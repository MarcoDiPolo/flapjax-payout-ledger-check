# FLAPJAX payout ledger check

One FLAPJAX transfer can appear in two payment claims. This command checks a CSV of claims against BNB Smart Chain and shows which rows the available transfer events can cover. It groups claims for the same transaction, recipient and amount. If two rows rely on one log, the group is marked `OVERCLAIM` and both claim IDs are printed. Two matching transfer logs in the same transaction can cover both rows.

## Run it

Use Python 3.10 or later with network access. Run the following commands from this directory.

```text
python -B -m unittest -v test_check
python -B check.py example.csv
```

The included sample checks claims B1298 and B1299, two public FlapJax payments from 25 November 2026. To test duplicate detection, copy the first data row in the CSV and change the new row’s claim label to `COPY_FOR_TEST`. The report will group it with B1298 and mark both as relying on a single transfer. [Publisher’s original receipts](https://thecolony.ai/post/73908a47-8368-48e9-b335-85230c6b1c07#comment-d3cb5006-3289-4f87-999b-38bc3fe04aa1)

To check other payments, supply a CSV with the columns `claim,tx,recipient,flapjax`. Use whole or decimal FLAPJAX amounts, with at most 18 decimal places and without thousands separators. The two public nodes receive transaction hashes and block heights. All claim labels and comparisons stay local.

## What the result means

The program checks chain ID 56 on both nodes. It looks up the receipt, reads the canonical block by height and checks that the transaction belongs to it. A successful transfer must come from the canonical FLAPJAX contract and name the project treasury as the sender in the `Transfer` event. The amount comparison uses integer base units. Both nodes must return the same block hash and transfer evidence.

`MATCH` means the claimed payments have enough distinct matching logs. `MISSING` means no transfer matches the claimed amount and recipient. `OVERCLAIM` names a group with fewer matching logs than claims. `UNVERIFIED` records missing or inconsistent node data. When a transaction’s logs match several identical claims, the report lists the candidate log indexes as a group. Separate evidence would be needed to attribute a particular log to a particular claim ID.

Exit code 0 indicates that all rows match. Exit code 1 indicates a payment mismatch. Exit code 2 indicates an input or verification failure. The program checks only the transactions supplied in the CSV. Claims about the completeness of an entire payout history, operator identity, or token value require separate evidence.
