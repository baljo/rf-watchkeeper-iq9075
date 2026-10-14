from unittest.mock import patch
import unittest
import acquisition_control as c

class DiscoveryTests(unittest.TestCase):
    def test_discovery_covers_legacy_and_excludes_retention_dashboard(self):
        lines='\n'.join(u+' enabled -' for u in ('rf-watchkeeper-scheduler.service','rf-watchkeeper-sensors.service','meteor-old.timer','satellite-preflight.service',*c.KEEP,'other.service'))
        with patch.object(c,'run',return_value=lines):
            self.assertEqual(c.discover(),['meteor-old.timer','rf-watchkeeper-scheduler.service','rf-watchkeeper-sensors.service','satellite-preflight.service'])

if __name__=='__main__':unittest.main()
