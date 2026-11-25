import tempfile
import unittest
from pathlib import Path

from check import amount_units, read_claims, reconcile


class LedgerCheckTests(unittest.TestCase):
    def test_distinct_claims_need_distinct_logs(self):
        claims = [('A', 'recipient', 100), ('B', 'recipient', 100)]
        single = reconcile(claims, [(12, 'recipient', 100)])[0]
        self.assertEqual((single['status'], single['matchingLogIndices']), ('OVERCLAIM', [12]))
        double = reconcile(claims, [(12, 'recipient', 100), (14, 'recipient', 100)])[0]
        self.assertEqual((double['status'], double['matchingLogIndices']), ('MATCH', [12, 14]))

    def test_wrong_recipient_and_wrong_amount_each_fail(self):
        claims = [('A', 'other', 100), ('B', 'recipient', 101)]
        rows = reconcile(claims, [(12, 'recipient', 100)])
        self.assertEqual([row['status'] for row in rows], ['MISSING', 'MISSING'])

    def test_integer_conversion_is_exact_at_18_decimals(self):
        self.assertEqual(amount_units('1000000.000000000000000001'), 10**24 + 1)
        with self.assertRaises(ValueError):
            amount_units('1.0000000000000000001')

    def test_duplicate_input_labels_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'test.csv'
            first_line = 'A,0x' + '1' * 64 + ',0x' + '2' * 40 + ',1\n'
            path.write_text('claim,tx,recipient,flapjax\n' + first_line * 2, encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'repeated claim'):
                read_claims(path)


if __name__ == '__main__':
    unittest.main()
