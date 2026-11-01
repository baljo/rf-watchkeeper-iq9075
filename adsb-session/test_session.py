import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('session',Path(__file__).with_name('session.py'))
s=importlib.util.module_from_spec(spec)
spec.loader.exec_module(s)

class SessionTests(unittest.TestCase):
    def test_beast_split_and_escape(self):
        data=bytes.fromhex('001a02030405')+bytes([26])+bytes.fromhex('8d40621d58c382d690c8ac2863a7')
        wire=b'\x1a3'+data.replace(b'\x1a',b'\x1a\x1a')
        for split in range(len(wire)):
            a,remaining=s.frames(wire[:split])
            b,remaining=s.frames(remaining+wire[split:])
            self.assertEqual(a+b,[(0x33,data)])
            self.assertEqual(remaining,b'')

    def test_expired_watchdog_restores(self):
        with tempfile.TemporaryDirectory() as d:
            lease=Path(d)/'lease.json'
            s.atomic(lease,dict(expiry=0,phase='capturing'))
            with patch.object(s,'LEASE',lease),patch.object(s,'restore') as restore:
                s.tick()
                restore.assert_called_once()

    def test_restore_never_starts_inactive_receivers(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            lease=root/'lease.json'
            before={'scheduler.service':dict(ActiveState='active',UnitFileState='enabled'),
                    'old.service':dict(ActiveState='inactive',UnitFileState='disabled'),
                    'dispatch.timer':dict(ActiveState='active',UnitFileState='enabled')}
            s.atomic(lease,dict(before=before,phase='capturing',session='test',start=0,expiry=1))
            with patch.object(s,'LEASE',lease),patch.object(s,'STATE',root),patch.object(s,'UNIT',root),patch.object(s,'ctl') as ctl,patch.object(s,'run',return_value=''),patch.object(s,'usb_owners',return_value=('usb',[])),patch.object(s,'props',side_effect=lambda u:before[u]),patch.object(s,'event'):
                s.restore()
                starts=[c.args for c in ctl.call_args_list if c.args[0]=='start']
                self.assertEqual(starts,[('start','scheduler.service'),('start','dispatch.timer')])
                self.assertFalse(lease.exists())

if __name__=='__main__':
    unittest.main()
