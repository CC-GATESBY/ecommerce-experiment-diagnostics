"""TARGET-02: apply the committed rules to original test membership exactly once."""
import argparse
import csv
from fractions import Fraction
import gzip
import hashlib
import json
import math
from pathlib import Path
import shutil
import time

import duckdb
import numpy as np

from ingest.ingest_criteo_source import HEADER
from uplift.ingest_criteo import bind_source, CSV_SHA, RECORDS
from uplift.split import row_id, assign, MEMBERSHIP_HEADER
from uplift.targeting import ROOT, RULES, CAPS, require, sha, dump, csv_out, group_sql, joint_table, evaluate

FROZEN_SHA = '3fae3c428d96aa607ed43d13996b2f0db08a34373334c082208bb9b4baebe5a2'
CONFIG_SHA = '324cf7a4c7e527480c5fc02116759c58969ac09ad5e0f41a10099958d6133228'
FROZEN_PATH = 'reports/targeting/frozen_rules.json'
PROTOCOL_PATH = 'docs/targeting_holdout_protocol.md'
MAX_NEW_BYTES = 4 * 2**30
MIN_FREE_BYTES = 150 * 2**30


def load_frozen(root=ROOT):
    """Check accepted byte identities; never call any training function."""
    require(sha(root/FROZEN_PATH) == FROZEN_SHA, 'frozen rule fingerprint mismatch')
    require(sha(root/'config/targeting.json') == CONFIG_SHA, 'original configuration changed')
    frozen = json.loads((root/FROZEN_PATH).read_text())
    cfg = json.loads((root/'config/targeting.json').read_text())
    require(frozen['version'] == 'criteo-targeting-rules-v1' and frozen['source_sha256'] == CSV_SHA,
            'rule version/source mismatch')
    require(frozen['policy_sha256'] == CONFIG_SHA and frozen['frozen_before_valid_effects'], 'rule freeze missing')
    for path, digest in frozen['code_sha256'].items():
        require(sha(root/path) == digest, 'TARGET-01 code/config changed: '+path)
    require(cfg['features'] == ['f0', 'f1'] and cfg['capacities_percent'] == CAPS, 'rule scope mismatch')
    require(all(g['response_rank'] == g['incremental_rank'] for g in frozen['groups']),
            'accepted identical policy ranks changed')
    return frozen, cfg


def extract_test(raw_path, member_path, source_sha, output, progress=None):
    """Traverse CSV logical ordinals; other splits are never cached or profiled."""
    counts = {s: [0, 0] for s in ('train', 'valid', 'test')}
    logical = hashlib.sha256(MEMBERSHIP_HEADER)
    sequences = {s: hashlib.sha256() for s in ('test', '0/test', '1/test')}
    start = time.monotonic()
    with Path(raw_path).open(newline='', encoding='utf-8') as f, gzip.open(member_path, 'rb') as m, Path(output).open('x', newline='') as target:
        reader = csv.reader(f, strict=True)
        require(next(reader, None) == HEADER and m.readline() == MEMBERSHIP_HEADER, 'header mismatch')
        writer = csv.writer(target, delimiter='\t', lineterminator='\n')
        writer.writerow(['row_id', 'f0', 'f1', 'treatment', 'conversion'])
        n = 0
        for ordinal, record in enumerate(reader):
            require(len(record) == 16 and record[12] in ('0', '1'), 'CSV width/treatment invalid')
            line = m.readline(256)
            fields = line.decode('ascii').rstrip('\n').split('\t')
            identity = row_id(source_sha, ordinal)
            split = assign(identity, record[12])
            require(fields == [str(ordinal), identity, record[12], split], 'membership alignment mismatch')
            logical.update(line)
            counts[split][int(record[12])] += 1
            if split == 'test':
                require(all(math.isfinite(float(v)) for v in record[:2]) and record[13] in ('0', '1'),
                        'test feature/conversion invalid')
                writer.writerow([identity, record[0], record[1], record[12], record[13]])
                for key in ('test', record[12]+'/test'):
                    sequences[key].update((identity+'\n').encode('ascii'))
            n += 1
            if progress and n % 500000 == 0:
                target.flush()
                progress(n, time.monotonic()-start)
        require(n > 0 and not m.read(1), 'empty input or extra membership')
    return dict(scanned_records=n, counts=counts, logical_sha256=logical.hexdigest(),
                sequence_sha256={s: d.hexdigest() for s, d in sequences.items()},
                extraction_seconds=time.monotonic()-start, retained_columns=['row_id', 'f0', 'f1', 'treatment', 'conversion'],
                retained_split='test', physical_other_split_bytes_traversed=True)


def apply_test(c, frozen):
    """Materialize ranks from features/ID first, then attach the original outcomes."""
    c.execute('CREATE TEMP TABLE scores(group_id INT,response_rank INT,incremental_rank INT,fallback BOOLEAN)')
    c.executemany('INSERT INTO scores VALUES (?,?,?,?)',
                  [(g['group_id'], g['response_rank'], g['incremental_rank'], g['fallback']) for g in frozen['groups']])
    c.execute("""CREATE TABLE selected_ranks AS WITH features AS (
        SELECT row_id,"""+group_sql(frozen['boundaries'])+""" AS group_id,
          sha256('target-v1|20260921|'||row_id) AS tie_hash FROM test_cache
        ) SELECT row_id,group_id,fallback,
          ROW_NUMBER() OVER(ORDER BY tie_hash ASC,row_id ASC) AS rank_random,
          ROW_NUMBER() OVER(ORDER BY response_rank ASC,tie_hash ASC,row_id ASC) AS rank_response,
          ROW_NUMBER() OVER(ORDER BY incremental_rank ASC,tie_hash ASC,row_id ASC) AS rank_incremental
        FROM features JOIN scores USING(group_id)""")
    n = c.execute('SELECT COUNT(*) FROM test_cache').fetchone()[0]
    require(n > 0 and c.execute('SELECT COUNT(*) FROM selected_ranks').fetchone()[0] == n, 'lost test rows')
    require(c.execute('SELECT COUNT(DISTINCT row_id) FROM test_cache').fetchone()[0] == n, 'duplicate test ID')
    require(c.execute('SELECT COUNT(*) FROM selected_ranks WHERE rank_response<>rank_incremental').fetchone()[0] == 0,
            'identical frozen policy ranks produced different membership')
    # There is no test-to-valid rename and no train/quantile query in this adapter.
    c.execute('CREATE TEMP VIEW ranked AS SELECT r.*, t.treatment,t.conversion FROM selected_ranks r JOIN test_cache t USING(row_id)')
    return n


def execute(run_id):
    require(run_id and all(x.isalnum() or x in '-_' for x in run_id), 'unsafe run ID')
    base = ROOT/'.local/target02'
    out = base/run_id
    out.mkdir(parents=True, exist_ok=False)
    start = time.monotonic()
    checks = []
    peak_bytes = 0
    min_free = shutil.disk_usage(ROOT).free
    c = None

    def budget():
        nonlocal peak_bytes, min_free
        used = sum(p.stat().st_size for p in base.rglob('*') if p.is_file())
        free = shutil.disk_usage(ROOT).free
        peak_bytes = max(peak_bytes, used)
        min_free = min(min_free, free)
        require(used <= MAX_NEW_BYTES and free >= MIN_FREE_BYTES, 'TARGET-02 resource budget exceeded')

    def check(name, expected, actual):
        checks.append(dict(check=name, expected=expected, actual=actual, passed=expected == actual))
        require(expected == actual, name)

    def progress(n, seconds):
        budget()
        print(json.dumps(dict(stage='align_and_extract_test', scanned_records=n, seconds=round(seconds, 1))), flush=True)

    try:
        budget()
        frozen, cfg = load_frozen()
        old = ROOT/'.local/target01/targeting-valid-01'
        prior = json.loads((old/'complete.json').read_text())
        require(prior['status'] == 'passed' and prior['frozen_rules_sha256'] == FROZEN_SHA, 'TARGET-01 acceptance invalid')
        for name in ('frozen_rules.json', 'coverage_comparison.csv', 'policy_differences.csv', 'stratum_summary.csv'):
            check('prior_accepted_'+name, sha(old/name), sha(ROOT/'reports/targeting'/name))
        protocol_sha = sha(ROOT/PROTOCOL_PATH)
        code_sha = {s: sha(ROOT/s) for s in ('uplift/targeting_holdout.py', 'tests/test_targeting_holdout.py')}
        # This receipt is closed before opening source features or computing test outcomes.
        dump(out/'protocol_before_test.json', dict(task='TARGET-02', rule_version=frozen['version'], split='test',
             frozen_rules_sha256=FROZEN_SHA, original_config_sha256=CONFIG_SHA, protocol_sha256=protocol_sha,
             code_sha256=code_sha, config=cfg, max_new_bytes=MAX_NEW_BYTES, minimum_free_bytes=MIN_FREE_BYTES,
             created_at_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())))
        raw, entry, binding = bind_source(ROOT)
        manifest = json.loads((ROOT/'data/criteo_split_manifest.json').read_text())
        member = ROOT/manifest['membership']['local_relative_path']
        require(member.resolve().is_relative_to(ROOT/'.local/t31/criteo-split-v1-01/complete') and not member.is_symlink(),
                'membership locator mismatch')
        proof = json.loads((member.parent/'run.json').read_text())
        validation = json.loads((member.parent/'validation.json').read_text())
        require(proof['status'] == 'complete' and proof['source_csv_sha256'] == CSV_SHA and
                validation['status'] == 'pass' and all(v['pass'] for v in validation['checks']) and
                manifest['run_id'] == frozen['split_run'] and manifest['split_rule']['seed'] == 20260917,
                'original split acceptance mismatch')
        check('membership_bytes', manifest['membership']['compressed_bytes'], member.stat().st_size)
        check('membership_sha_before', manifest['membership']['compressed_sha256'], sha(member))
        protected = {str(p): [p.stat().st_size, p.stat().st_mtime_ns] for p in (raw, member)}
        print(json.dumps(dict(stage='protocol_and_source_bound', source_bytes=raw.stat().st_size,
                             rules_sha256=FROZEN_SHA, protocol_sha256=protocol_sha)), flush=True)
        meta = extract_test(raw, member, CSV_SHA, out/'test.tsv', progress)
        check('source_records', RECORDS, meta['scanned_records'])
        check('logical_membership_sha', manifest['membership']['logical_sha256'], meta['logical_sha256'])
        for split in ('train', 'valid', 'test'):
            for arm in (0, 1):
                qc = next(g for g in manifest['qc']['groups'] if g['split'] == split and g['treatment'] == str(arm))
                check('membership_n_'+split+'_'+str(arm), qc['n'], meta['counts'][split][arm])
        for key, digest in meta['sequence_sha256'].items():
            check('test_sequence_'+key, manifest['membership']['sequence_sha256'][key], digest)
        meta.update(cache_bytes=(out/'test.tsv').stat().st_size, cache_sha256=sha(out/'test.tsv'))
        dump(out/'cache_complete.json', meta)
        budget()
        c = duckdb.connect(str(out/'analysis.duckdb'))
        c.execute("SET threads=4; SET memory_limit='2GB'; SET TimeZone='UTC'; SET max_temp_directory_size='2GB'")
        c.execute('SET temp_directory=?', [str(out/'temp')])
        c.execute("CREATE TABLE test_cache AS SELECT * FROM read_csv(?,delim='\t',header=true,columns={'row_id':'VARCHAR','f0':'DOUBLE','f1':'DOUBLE','treatment':'TINYINT','conversion':'TINYINT'},strict_mode=true)", [str(out/'test.tsv')])
        n = apply_test(c, frozen)
        check('test_n', sum(meta['counts']['test']), n)
        dump(out/'selection_before_evaluation.json', dict(status='ranks_materialized', split='test', n=n,
             rule_sha256=FROZEN_SHA, rank_table_has_treatment_or_conversion=False,
             created_at_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())))
        for rule in RULES:
            col = 'rank_'+rule.lower()
            bounds = c.execute('SELECT MIN('+col+'),MAX('+col+'),COUNT(DISTINCT '+col+') FROM selected_ranks').fetchone()
            check('complete_nested_rank_'+rule, [1, n, n], list(bounds))
        for arm in (0, 1):
            qc = next(g for g in manifest['qc']['groups'] if g['split'] == 'test' and g['treatment'] == str(arm))
            actual = c.execute('SELECT COUNT(*),SUM(conversion) FROM test_cache WHERE treatment=?', [arm]).fetchone()
            check('test_arm_n_conversion_'+str(arm), [qc['n'], qc['conversion']], list(actual))
        budget()
        joint, specs = joint_table(c, n, cfg)
        coverage, diffs, _ = evaluate(joint, specs, cfg)
        # Independent SQL over selected records, rather than deriving expected counts from joint masks.
        exact_g = {}
        for r in coverage:
            check('capacity_'+r['rule']+'_'+str(r['capacity_percent']), r['capacity_percent']*n//100, r['selected_n'])
            col = 'rank_'+r['rule'].lower()
            actual = c.execute('SELECT COUNT(*) FILTER(WHERE treatment=0),COUNT(*) FILTER(WHERE treatment=1),SUM(conversion) FILTER(WHERE treatment=0),SUM(conversion) FILTER(WHERE treatment=1) FROM test_cache JOIN selected_ranks USING(row_id) WHERE '+col+'<=?', [r['selected_n']]).fetchone()
            check('direct_selected_'+r['rule']+'_'+str(r['capacity_percent']), list(actual),
                  [r[k] for k in ('control_n', 'treatment_n', 'conversion_control', 'conversion_treatment')])
            if actual[0] and actual[1]:
                exact = Fraction(10000*r['selected_n'], n)*(Fraction(actual[3], actual[1])-Fraction(actual[2], actual[0]))
                exact_g[r['rule'], r['capacity_percent']] = exact
                check('fraction_G_'+r['rule']+'_'+str(r['capacity_percent']), True, abs(float(exact)-r['G']) < 1e-12)
            r['fallback_selected_n'] = c.execute('SELECT COUNT(*) FROM selected_ranks WHERE fallback AND '+col+'<=?', [r['selected_n']]).fetchone()[0]
        for r in diffs:
            first, second = r['contrast'].split('_minus_')
            if (first, r['capacity_percent']) in exact_g and (second, r['capacity_percent']) in exact_g:
                exact = exact_g[first, r['capacity_percent']]-exact_g[second, r['capacity_percent']]
                check('fraction_diff_'+r['contrast']+'_'+str(r['capacity_percent']), True, abs(float(exact)-r['G_difference']) < 1e-12)
            if r['capacity_percent'] == 100 or r['contrast'] == 'INCREMENTAL_minus_RESPONSE':
                check('identical_policy_'+r['contrast']+'_'+str(r['capacity_percent']),
                      [r['selected_n'], 0.0, 0.0, 0.0], [r['overlap_n'], r['G_difference'], r['ci95_low'], r['ci95_high']])
        check('frozen_rules_after', FROZEN_SHA, sha(ROOT/FROZEN_PATH))
        check('config_after', CONFIG_SHA, sha(ROOT/'config/targeting.json'))
        check('protocol_after', protocol_sha, sha(ROOT/PROTOCOL_PATH))
        check('code_after', code_sha, {s: sha(ROOT/s) for s in code_sha})
        check('inputs_stat_unchanged', protected, {str(p): [p.stat().st_size, p.stat().st_mtime_ns] for p in (raw, member)})
        check('raw_sha_after', CSV_SHA, sha(raw))
        check('membership_sha_after', manifest['membership']['compressed_sha256'], sha(member))
        csv_out(out/'coverage_comparison.csv', [dict(split='test', rule_version=frozen['version'], **r) for r in coverage])
        csv_out(out/'policy_differences.csv', [dict(split='test', rule_version=frozen['version'], **r) for r in diffs])
        dump(out/'joint_types_private.json', joint)
        c.execute('CHECKPOINT')
        c.close()
        c = None
        budget()
        dump(out/'complete.json', dict(status='passed', task='TARGET-02', run_id=run_id, split='test', checks=checks,
             frozen_rules_sha256=FROZEN_SHA, protocol_sha256=protocol_sha, code_sha256=code_sha,
             source_binding=binding, cache=meta, test_n=n, joint_types=len(joint), bootstrap_repetitions=cfg['bootstrap_repetitions'],
             elapsed_seconds=round(time.monotonic()-start, 3), sampled_peak_new_bytes=peak_bytes, minimum_free_bytes=min_free,
             peak_memory='not_measured', versions=dict(duckdb=duckdb.__version__, numpy=np.__version__)))
        print(json.dumps(dict(status='passed', checks=len(checks), elapsed_seconds=round(time.monotonic()-start, 3))), flush=True)
    except BaseException as exc:
        dump(out/('failed-'+str(time.time_ns())+'.json'), dict(status='failed', error=type(exc).__name__+': '+str(exc), checks=checks))
        raise
    finally:
        if c is not None:
            c.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-id', required=True)
    execute(parser.parse_args().run_id)
