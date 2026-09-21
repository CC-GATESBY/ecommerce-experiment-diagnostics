"""Versioned user-key assignment. No outcome fields enter this interface."""
import hashlib
import re
import numpy as np

PREFIX = b'rees46-aa-assignment-v1|'


def prepare_keys(keys):
    if not keys or any(not isinstance(k,str) or re.fullmatch('[0-9a-f]{64}',k) is None for k in keys):
        raise ValueError('nonempty canonical cohort keys required')
    if len(keys)!=len(set(keys)):raise ValueError('duplicate cohort key')
    return tuple(k.encode('ascii') for k in keys)


def assign(keys, experiment_id):
    if not isinstance(experiment_id,str) or re.fullmatch(r'rees46-aa-v1-\d{4}',experiment_id,flags=re.ASCII) is None:
        raise ValueError('invalid experiment ID')
    if not 1<=int(experiment_id[-4:])<=300:raise ValueError('unplanned experiment ID')
    prefix=PREFIX+experiment_id.encode('ascii')+b'|'
    return np.fromiter((int.from_bytes(hashlib.sha256(prefix+k).digest()[:8],'big')>=2**63 for k in keys),
                       dtype=np.bool_,count=len(keys))
