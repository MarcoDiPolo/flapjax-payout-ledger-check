"""Reconcile FLAPJAX ledger rows with distinct BSC Transfer logs."""

import argparse
import csv
import json
import re
import sys
import urllib.request
from collections import defaultdict
from pathlib import Path


TOKEN = '0x90c8889f428f9ebb77bb8f15cad3a50a9ac680df'
TREASURY = '0x7c34e9e21ee28a49ff0b84b61774119e6633359f'
TRANSFER = '0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef'
NODES = ['https://bsc-rpc.publicnode.com', 'https://bsc-dataseed.bnbchain.org']


def amount_units(value):
    if not re.fullmatch(r'[0-9]+(?:\.[0-9]{1,18})?', value):
        raise ValueError(f'Invalid FLAPJAX amount {value!r}. Use a decimal with at most 18 places.')
    integer, _, fraction = value.partition('.')
    return int(integer) * 10**18 + int(fraction.ljust(18, '0'))


def read_claims(path):
    claims = defaultdict(list)
    seen = set()
    with path.open(encoding='utf-8-sig', newline='') as file:
        reader = csv.DictReader(file)
        if reader.fieldnames != ['claim', 'tx', 'recipient', 'flapjax']:
            raise ValueError('Expected CSV header claim,tx,recipient,flapjax')
        for line, row in enumerate(reader, 2):
            if None in row or any(value is None for value in row.values()):
                raise ValueError(f'Unexpected column count on line {line}.')
            claim, tx, recipient, amount = (row[k].strip() for k in reader.fieldnames)
            if not claim or claim in seen:
                raise ValueError(f'Empty or repeated claim identifier on line {line}.')
            if not re.fullmatch(r'0x[0-9a-fA-F]{64}', tx) or not re.fullmatch(r'0x[0-9a-fA-F]{40}', recipient):
                raise ValueError(f'Invalid transaction or recipient on line {line}.')
            seen.add(claim)
            claims[tx.lower()].append((claim, recipient.lower(), amount_units(amount)))
    if not claims:
        raise ValueError('CSV contains no claims.')
    return claims


def rpc(node, method, params):
    payload = json.dumps(dict(jsonrpc='2.0', id=1, method=method, params=params)).encode()
    request = urllib.request.Request(node, payload, {'Content-Type': 'application/json', 'User-Agent': 'FlapJaxLedgerCheck/1.0'})
    with urllib.request.urlopen(request, timeout=15) as response:
        data = json.load(response)
    if 'error' in data or 'result' not in data:
        raise ValueError(str(data.get('error', 'Missing JSON-RPC result')))
    return data['result']


def receipt_evidence(node, tx):
    receipt = rpc(node, 'eth_getTransactionReceipt', [tx])
    if not receipt:
        raise ValueError('Receipt unavailable.')
    if receipt['transactionHash'].lower() != tx:
        raise ValueError('Receipt transaction hash differs from the request.')
    block = rpc(node, 'eth_getBlockByNumber', [receipt['blockNumber'], False])
    if not block or block['hash'].lower() != receipt['blockHash'].lower() or tx not in [entry.lower() for entry in block['transactions']]:
        raise ValueError('Node could not confirm the transaction in its canonical block.')
    events = []
    if int(receipt['status'], 16) == 1:
        for log in receipt['logs']:
            topics = [item.lower() for item in log['topics']]
            if log['address'].lower() != TOKEN or len(topics) != 3 or topics[0] != TRANSFER:
                continue
            if topics[1] != '0x' + TREASURY[2:].zfill(64):
                continue
            if log.get('removed') or log['transactionHash'].lower() != tx or log['blockHash'].lower() != block['hash'].lower():
                raise ValueError('Log identity disagrees with its receipt.')
            events.append((int(log['logIndex'], 16), '0x' + topics[2][-40:], int(log['data'], 16)))
    if len({event[0] for event in events}) != len(events):
        raise ValueError('Duplicate log index in the receipt.')
    return block['hash'].lower(), int(receipt['blockNumber'], 16), int(receipt['status'], 16), sorted(events)


def reconcile(claims, events):
    by_payment = defaultdict(list)
    by_claim = defaultdict(list)
    for index, recipient, units in events:
        by_payment[(recipient, units)].append(index)
    for name, recipient, units in claims:
        by_claim[(recipient, units)].append(name)
    rows = []
    for key, names in by_claim.items():
        indices = by_payment[key]
        if len(indices) >= len(names):
            status = 'MATCH'
        elif indices:
            status = 'OVERCLAIM'
        else:
            status = 'MISSING'
        rows.append(dict(claims=names, recipient=key[0], tokenUnits=str(key[1]), matchingLogIndices=indices, status=status))
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('csv', type=Path)
    args = parser.parse_args()
    claims = read_claims(args.csv)
    for node in NODES:
        if int(rpc(node, 'eth_chainId', []), 16) != 56:
            raise ValueError('Expected BNB Smart Chain (56).')
    reports = []
    for tx, expected in claims.items():
        try:
            primary, other = (receipt_evidence(node, tx) for node in NODES)
            if primary != other:
                raise ValueError('The two nodes disagree on the canonical payment evidence.')
            block_hash, height, receipt_status, events = primary
            groups = reconcile(expected, events)
            reports.append(dict(tx=tx, block=height, blockHash=block_hash, receiptStatus=receipt_status,
                                status='MATCH' if all(group['status'] == 'MATCH' for group in groups) else 'MISMATCH', groups=groups))
        except (ValueError, OSError, KeyError, TypeError) as error:
            reports.append(dict(tx=tx, status='UNVERIFIED', claims=[row[0] for row in expected], reason=str(error)))
    print(json.dumps(dict(chainId=56, token=TOKEN, treasury=TREASURY, nodes=NODES, transactions=reports), indent=2))
    if any(row['status'] == 'UNVERIFIED' for row in reports):
        return 2
    return int(any(row['status'] == 'MISMATCH' for row in reports))


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (ValueError, OSError, KeyError, TypeError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(2)
