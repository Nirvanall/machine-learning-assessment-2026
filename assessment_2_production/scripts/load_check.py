"""Small HTTP burst check, not an autoscaling/SLO certification.

Run against a local/staging service you are authorized to test. Supply an Entra token
through LOAD_TEST_BEARER_TOKEN for an authenticated endpoint; never put it in argv/logs.
"""
import argparse
import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from statistics import median
from time import perf_counter
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://127.0.0.1:8000')
    parser.add_argument('--requests', type=int, default=100)
    parser.add_argument('--concurrency', type=int, default=2)
    parser.add_argument('--payload', type=Path, default=Path(__file__).resolve().parents[1] / 'examples/predict.json')
    args = parser.parse_args()
    if args.requests < 1 or not 1 <= args.concurrency <= 32:
        parser.error('Use positive requests and concurrency 1–32')
    payload = args.payload.read_bytes()
    headers = {'Content-Type':'application/json'}
    token = os.environ.get('LOAD_TEST_BEARER_TOKEN')
    if token: headers['Authorization'] = f'Bearer {token}'
    def one(_):
        start = perf_counter()
        try:
            with urlopen(Request(args.url.rstrip('/')+'/predict',data=payload,headers=headers),timeout=10) as response:
                result = json.load(response)
                valid = (result.get('is_success') is True and result.get('predicted_owner_range')
                         in ['0 - 20000', '20000 - 100000', '100000 - 200000000']
                         and 0 <= result.get('probability', -1) <= 1 and bool(result.get('model_version')))
                return 200 if valid else 500, 1000*(perf_counter()-start)
        except HTTPError as exc: return exc.code,1000*(perf_counter()-start)
        except Exception: return 0,1000*(perf_counter()-start)
    start=perf_counter()
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        results=list(pool.map(one,range(args.requests)))
    elapsed=perf_counter()-start
    durations=sorted(duration for _,duration in results)
    summary={'requests':args.requests,'concurrency':args.concurrency,
             'successes':sum(code==200 for code,_ in results),'elapsed_seconds':round(elapsed,3),
             'requests_per_second':round(args.requests/elapsed,2),'p50_ms':round(median(durations),2),
             'p95_ms':round(durations[int(.95*(len(durations)-1))],2),
             'status_counts':{str(code):sum(c==code for c,_ in results) for code in sorted({c for c,_ in results})}}
    print(json.dumps(summary,indent=2))
    raise SystemExit(0 if summary['successes']==args.requests else 1)

if __name__=='__main__':main()
