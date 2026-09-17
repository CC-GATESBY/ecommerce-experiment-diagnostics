"""Synthetic literal contracts and bounded failure cases; no real CSV scan."""

import csv
from decimal import Decimal
import gzip
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
import subprocess
import sys
import os
from unittest.mock import patch

from ingest.ingest import IngestError
from uplift import split as s
from uplift.ingest_criteo import HEADER, rows, validate_entry

SYNTHETIC_SHA = "0" * 64


class CriteoSplitTests(unittest.TestCase):
    def setUp(self):
        parent = s.BASE / "synthetic"
        parent.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="synthetic-", dir=parent)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "synthetic.csv"
        one = ["1"]*12 + ["0", "0", "1", "0"]
        self.fixture = [one.copy(), one.copy(), ["2"]*12+["1", "1", "1", "1"],
                        ["3"]*12+["1", "0", "0", "0"]]
        self.write(self.fixture)

    def write(self, values, header=HEADER):
        with self.source.open("w", encoding="utf-8", newline="") as f:
            w = csv.writer(f); w.writerow(header); w.writerows(values)

    def literal_expected(self, fixture):
        # Written from the frozen formula, without production helpers.
        text = "source_record_ordinal\trow_id\ttreatment\tsplit\n"
        for i, row in enumerate(fixture):
            payload = "criteo-row-v1|0000000000000000000000000000000000000000000000000000000000000000|" + str(i)
            rid = hashlib.sha256(payload.encode()).hexdigest()
            raw = hashlib.sha256(("criteo-split-v1|20260917|t="+row[12]+"|"+rid).encode()).digest()
            number = int.from_bytes(raw[:8], byteorder="big", signed=False)
            name = "train" if number < 11068046444225730969 else "valid" if number < 14757395258967641292 else "test"
            text += f"{i}\t{rid}\t{row[12]}\t{name}\n"
        return text.encode()

    def test_duplicate_content_distinct_ids_literal_formula(self):
        out = self.root / "m.gz"; summary = s.generate(self.source, SYNTHETIC_SHA, out)
        actual = gzip.decompress(out.read_bytes())
        self.assertEqual(actual, self.literal_expected(self.fixture))
        values = list(csv.reader(io.StringIO(actual.decode()), delimiter="\t"))[1:]
        self.assertEqual([v[0] for v in values], ["0", "1", "2", "3"])
        self.assertNotEqual(values[0][1], values[1][1])
        self.assertEqual(summary["logical_sha256"], hashlib.sha256(actual).hexdigest())

    def test_same_source_ordinal_id_and_source_namespace(self):
        expected = hashlib.sha256(("criteo-row-v1|"+SYNTHETIC_SHA+"|0").encode()).hexdigest()
        self.assertEqual(s.row_id(SYNTHETIC_SHA, 0), expected)
        self.assertEqual(s.row_id(SYNTHETIC_SHA, 0), s.row_id(SYNTHETIC_SHA, 0))
        self.assertNotEqual(s.row_id(SYNTHETIC_SHA, 0), s.row_id("f"*64, 0))
        with self.assertRaises(IngestError): s.row_id(SYNTHETIC_SHA, -1)
        with self.assertRaises(IngestError): s.row_id(SYNTHETIC_SHA, True)

    def test_fixed_seed_repeated_gzip_bytes_and_sequences(self):
        a,b = self.root/"a.gz", self.root/"b.gz"
        x=s.generate(self.source,SYNTHETIC_SHA,a); y=s.generate(self.source,SYNTHETIC_SHA,b)
        self.assertEqual(a.read_bytes(),b.read_bytes())
        for k in ["logical_sha256","compressed_sha256","sequence_sha256","split_counts"]:
            self.assertEqual(x[k],y[k])
        self.assertEqual(a.read_bytes()[4:8],b"\0\0\0\0")

    def test_csv_quotes_multiline_empty_fields_and_header_exclusion(self):
        self.fixture[0][:3]=['synthetic, "quoted"','synthetic\nmultiline','']
        self.write(self.fixture)
        self.assertEqual([i for i,_ in rows(self.source)],[0,1,2,3])
        out=self.root/"m.gz"; a=s.generate(self.source,SYNTHETIC_SHA,out)
        b=s.independent_check(self.source,SYNTHETIC_SHA,out)
        self.assertEqual(a["n"],4);self.assertEqual(b["n"],4)
        self.assertEqual(gzip.decompress(out.read_bytes()),self.literal_expected(self.fixture))

    def test_empty_and_header_only_rejected(self):
        for data in ['',','.join(HEADER)+'\n']:
            self.source.write_text(data)
            with self.assertRaises(IngestError): list(rows(self.source))

    def test_short_long_wrong_header(self):
        for values,header in [([self.fixture[0][:-1]],HEADER),([self.fixture[0]+['x']],HEADER),(self.fixture,['wrong']+HEADER[1:])]:
            self.write(values,header)
            with self.assertRaises(IngestError): list(rows(self.source))

    def test_invalid_treatment_and_qc_label(self):
        for col in [12,13,14,15]:
            self.fixture[0][col]='2';self.write(self.fixture)
            with self.assertRaises(IngestError): list(rows(self.source))
            self.fixture[0][col]='0'
        with self.assertRaises(IngestError):s.assign('a'*64,'01')

    def test_exact_threshold_sides(self):
        expected=[(0,'train'),(11068046444225730968,'train'),(11068046444225730969,'valid'),
                  (14757395258967641291,'valid'),(14757395258967641292,'test'),(18446744073709551615,'test')]
        for h,label in expected:self.assertEqual(s.choose_uint64(h),label)
        for bad in [-1,2**64,0.6]:
            with self.assertRaises(IngestError):s.choose_uint64(bad)

    def test_outcome_and_feature_change_does_not_reassign(self):
        a=self.root/'before.gz';b=self.root/'after.gz'
        s.generate(self.source,SYNTHETIC_SHA,a)
        for row in self.fixture:
            row[:12]=['changed synthetic feature']*12
            row[13:]=['1' if x=='0' else '0' for x in row[13:]]
        self.write(self.fixture);s.generate(self.source,SYNTHETIC_SHA,b)
        self.assertEqual(a.read_bytes(),b.read_bytes())

    def test_output_exists_rejected_without_change(self):
        out=self.root/'m.gz';out.write_bytes(b'existing synthetic')
        with self.assertRaises(FileExistsError):s.generate(self.source,SYNTHETIC_SHA,out)
        self.assertEqual(out.read_bytes(),b'existing synthetic')

    def test_independent_full_output_and_source_counts(self):
        out=self.root/'m.gz';a=s.generate(self.source,SYNTHETIC_SHA,out);b=s.independent_check(self.source,SYNTHETIC_SHA,out)
        expected={'treatment':{'0':2,'1':2},'conversion':{'0':3,'1':1},'visit':{'0':1,'1':3},'exposure':{'0':3,'1':1}}
        self.assertEqual(a['source_binary_counts'],expected);self.assertEqual(b['source_binary_counts'],expected)
        self.assertTrue(all(x['pass'] for x in s.validate(a,b,4,expected,sanity=False)))
        b['logical_sha256']='bad'
        with self.assertRaises(IngestError):s.validate(a,b,4,expected,sanity=False)

    def test_member_missing_extra_or_tampered_rejected(self):
        data=self.literal_expected(self.fixture)
        variants=[data.splitlines(keepends=True)[0]+b''.join(data.splitlines(keepends=True)[2:]),
                  data+data.splitlines(keepends=True)[1],data.replace(b'\t0\t',b'\t1\t',1)]
        for i,payload in enumerate(variants):
            out=self.root/f'bad{i}.gz';out.write_bytes(gzip.compress(payload))
            with self.assertRaises(IngestError):s.independent_check(self.source,SYNTHETIC_SHA,out)

    def test_broken_gzip_rejected(self):
        out=self.root/'m.gz';s.generate(self.source,SYNTHETIC_SHA,out)
        out.write_bytes(out.read_bytes()[:-4])
        with self.assertRaises(EOFError):s.independent_check(self.source,SYNTHETIC_SHA,out)

    def test_run_failure_stays_staging_no_complete(self):
        with patch.object(s,'BASE',self.root),patch.object(s,'bind_source',side_effect=IngestError('synthetic')):
            with self.assertRaises(IngestError):s.run('synthetic-failure')
            with self.assertRaises(FileExistsError):s.run('synthetic-failure')
        run=self.root/'synthetic-failure'
        self.assertFalse((run/'complete').exists())
        self.assertEqual(json.loads((run/'failed.json').read_text())['status'],'failed')

    def test_no_builtin_hash_and_split_inputs_fixed(self):
        import ast,inspect
        tree=ast.parse(inspect.getsource(s))
        self.assertFalse(any(isinstance(x,ast.Call) and isinstance(x.func,ast.Name) and x.func.id=='hash' for x in ast.walk(tree)))
        self.assertEqual(list(inspect.signature(s.assign).parameters),['identity','treatment'])
        self.assertEqual(s.SEED,20260917)

    def test_wrong_manifest_identity_rejected_without_raw_access(self):
        entry=json.loads((s.ROOT/'data/manifest.json').read_text())['additional_sources']['criteo_uplift_v2_1_corrected']
        for key,value in [('source_id','old'),('version','old25M'),('validation_status','pending')]:
            changed=json.loads(json.dumps(entry));changed[key]=value
            with self.assertRaises(IngestError):validate_entry(changed)
        for key,value in [('sha256','0'*64),('bytes',0),('header',[]),('full_record_count',0)]:
            changed=json.loads(json.dumps(entry));changed['files'][1][key]=value
            with self.assertRaises(IngestError):validate_entry(changed)

    def test_sanity_guard_is_frozen_not_seed_selection(self):
        expected={'treatment':{'0':2,'1':2},'conversion':{'0':3,'1':1},'visit':{'0':1,'1':3},'exposure':{'0':3,'1':1}}
        out=self.root/'m.gz';a=s.generate(self.source,SYNTHETIC_SHA,out);b=s.independent_check(self.source,SYNTHETIC_SHA,out)
        with self.assertRaisesRegex(IngestError,'sanity'):s.validate(a,b,4,expected)

    def test_qc_rates_denominators(self):
        out=self.root/'m.gz';a=s.generate(self.source,SYNTHETIC_SHA,out)
        for row in s.qc_rows(a):
            for label in ['conversion','visit','exposure']:
                self.assertEqual(row[label+'_rate'],str(Decimal(row[label])/row['n']) if row['n'] else None)

    def test_literal_golden_assignment_and_digests(self):
        out=self.root/'golden.gz';a=s.generate(self.source,SYNTHETIC_SHA,out)
        expected_ids=['eaaa60cdf341b6793beeec0bb1f246d8ecbd1ae371e2f6e937aae84d556ed230',
                      '0cfb1e4b5f6b98a43a66f84a37540369f349426191aeda5213063510d9b8effd',
                      '0a88597227cc1abac2e20f7cebfff239c0e19bfddaac186588bac169dbee5998',
                      'bb4d5eba07a834dd9142803cbe52abb3a7698ba800135a76b98b03c286a394bf']
        members=list(csv.reader(io.StringIO(gzip.decompress(out.read_bytes()).decode()),delimiter='\t'))[1:]
        self.assertEqual([v[1] for v in members],expected_ids)
        self.assertEqual([v[3] for v in members],['train','valid','test','train'])
        self.assertEqual({k:v['n'] for k,v in a['split_counts'].items()},{'train':2,'valid':1,'test':1})
        self.assertEqual(a['sequence_sha256']['train'],hashlib.sha256((expected_ids[0]+'\n'+expected_ids[3]+'\n').encode()).hexdigest())

    def test_cross_process_hash_seed_does_not_change_bytes(self):
        outputs=[]
        for seed in ['1','123']:
            out=self.root/('process-'+seed+'.gz');outputs.append(out)
            code='from uplift.split import generate;import sys;generate(sys.argv[1],sys.argv[2],sys.argv[3])'
            subprocess.run([sys.executable,'-c',code,str(self.source),SYNTHETIC_SHA,str(out)],
                           cwd=s.ROOT,env={**os.environ,'PYTHONHASHSEED':seed},check=True,capture_output=True)
        self.assertEqual(outputs[0].read_bytes(),outputs[1].read_bytes())

    def test_mid_generation_failure_never_publishes(self):
        def broken(path,sha,dest,progress):
            dest.write_bytes(b'synthetic incomplete gzip')
            raise IngestError('synthetic write interruption')
        with patch.object(s,'BASE',self.root),patch.object(s,'bind_source',return_value=(self.source,{},{})),patch.object(s,'generate',side_effect=broken):
            with self.assertRaises(IngestError):s.run('synthetic-mid-write')
        run=self.root/'synthetic-mid-write'
        self.assertTrue((run/'staging/split_membership.tsv.gz').exists())
        self.assertFalse((run/'complete').exists())
        self.assertEqual(json.loads((run/'failed.json').read_text())['stage'],'generate')

    def test_readonly_staging_publication_order(self):
        staging=self.root/'staging';complete=self.root/'complete';staging.mkdir()
        member=staging/'synthetic.gz';member.write_bytes(b'synthetic');member.chmod(0o444)
        staging.chmod(0o555)
        s.publish_validated(staging,complete)
        self.addCleanup(lambda: complete.chmod(0o755))
        self.assertFalse(staging.exists())
        self.assertEqual((complete/'synthetic.gz').read_bytes(),b'synthetic')
        self.assertEqual((complete/'synthetic.gz').stat().st_mode & 0o777,0o444)
        self.assertEqual(complete.stat().st_mode & 0o777,0o555)
        with self.assertRaises(IngestError):s.publish_validated(staging,complete)

    def test_incomplete_failure_cannot_resume(self):
        run=self.root/'synthetic-resume';(run/'staging').mkdir(parents=True)
        (run/'failed.json').write_text(json.dumps({'stage':'generate','error_type':'PermissionError'}))
        with patch.object(s,'BASE',self.root),self.assertRaises(IngestError):
            s.resume_validated('synthetic-resume')
        self.assertFalse((run/'complete').exists())


if __name__=='__main__':
    unittest.main()
