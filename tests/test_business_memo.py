"""Evidence and decision-boundary regression for the fixed one-page memo."""
import ast
from copy import deepcopy
from decimal import Decimal
from pathlib import Path
import sys
import unittest

from scripts.check_business_memo import ROOT,FORBIDDEN,evidence,percent,read_csv,validate


class BusinessMemoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.memo=(ROOT/'reports/business_decision_memo.md').read_text()
        cls.rows=read_csv(ROOT,'reports/business_decision_memo_evidence.csv')

    def rejected(self,text,rows=None):
        with self.assertRaises(AssertionError):validate(text,self.rows if rows is None else rows)

    def test_current_evidence_and_document(self):
        result=validate(self.memo,self.rows)
        self.assertEqual(result['status'],'passed');self.assertEqual(result['evidence_rows'],20)

    def test_amount_decimal_is_exact(self):
        values={r['claim_id']:r['value'] for r in evidence()}
        self.assertEqual(Decimal(values['electronics_purchase_amount']),Decimal('8750242.89'))
        self.assertEqual(Decimal(values['unknown_purchase_amount']),Decimal('1209130.91'))
        self.rejected(self.memo.replace('8,750,242.89','8,750,242.88'))

    def test_percentage_rounding_and_drift(self):
        self.assertEqual(percent(Decimal('0.7544203689597409')),'75.4420%')
        self.rejected(self.memo.replace('75.4420%','75.4421%'))

    def test_month_users_must_come_from_month_check(self):
        source=next(r for r in self.rows if r['claim_id']=='month_active_users')
        self.assertEqual(source['source_row_or_metric'],'check=month_active_users; field=actual')
        self.rejected(self.memo.replace('151,121','322,660'))
        self.rejected(self.memo.replace('各品类用户集合重叠，不能相加','各品类用户可相加'))

    def test_evidence_tamper_rejected(self):
        rows=deepcopy(self.rows);rows[0]['value']='322660';self.rejected(self.memo,rows)

    def test_forbidden_assertions_rejected(self):
        for phrase in FORBIDDEN:
            with self.subTest(phrase=phrase):self.rejected(self.memo+'\n'+phrase)

    def test_priority_action_requires_evidence_and_validation(self):
        self.rejected(self.memo.replace('按category_code字段规范和来源映射','按经验'))
        self.rejected(self.memo.replace('并对账归类解释前后的金额结构','并检查金额'))

    def test_at_least_three_alternatives(self):
        text='\n'.join(s for s in self.memo.splitlines() if not s.startswith(('- electronics可能','- unknown可能')))
        self.rejected(text)

    def test_current_decision_and_change_conditions(self):
        self.rejected(self.memo.replace('建议暂不调整策略','建议立即调整策略'))
        self.rejected(self.memo.replace('若unknown仍无法可靠归类','不管是否可靠归类'))

    def test_no_invented_action_threshold(self):
        self.rejected(self.memo+'\n超过70%就行动。')

    def test_concise_chinese_memo(self):
        self.rejected(self.memo+'\n'+'补充'*600)

    def test_checker_imports_only_standard_library(self):
        tree=ast.parse((ROOT/'scripts/check_business_memo.py').read_text())
        imports=[]
        for node in ast.walk(tree):
            if isinstance(node,ast.Import):imports.extend(n.name.split('.')[0] for n in node.names)
            elif isinstance(node,ast.ImportFrom):imports.append(node.module.split('.')[0])
        self.assertTrue(set(imports)<=sys.stdlib_module_names)
        self.assertFalse(any(isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='float' for n in ast.walk(tree)))
