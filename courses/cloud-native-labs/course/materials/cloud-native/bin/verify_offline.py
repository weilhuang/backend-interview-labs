#!/usr/bin/env python3
"""不启动Java或Docker；拒绝零测试的离线入口。"""
import argparse,pathlib,sys,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tests'))
from verification_guard import VerificationSetupError

def load_suite(pattern='test_*.py'):
    suite=unittest.TestLoader().discover(str(ROOT/'tests'),pattern=pattern)
    if suite.countTestCases()==0:raise VerificationSetupError('No tests selected; zero cases is not PASS')
    return suite

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--pattern',default='test_*.py');args=parser.parse_args()
    try:suite=load_suite(args.pattern)
    except VerificationSetupError as error:parser.exit(2,str(error)+'\n')
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)
