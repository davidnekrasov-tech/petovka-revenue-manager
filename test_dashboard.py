import base64
import hashlib
import re
import unittest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from dashboard import router

class DashboardTests(unittest.TestCase):
    def test_shell_has_no_data_and_matching_csp(self):
        app=FastAPI();app.include_router(router)
        with TestClient(app) as client:
            r=client.get('/dashboard')
        self.assertEqual(r.status_code,200)
        self.assertEqual(r.headers['cache-control'],'no-store')
        script=re.search(r'<script>(.*?)</script>',r.text,re.S).group(1)
        digest=base64.b64encode(hashlib.sha256(script.encode()).digest()).decode()
        self.assertIn('sha256-'+digest,r.headers['content-security-policy'])
        self.assertIn("connect-src 'self'",r.headers['content-security-policy'])
        self.assertNotIn('localStorage',script)
        self.assertNotIn('sessionStorage',script)
        self.assertNotIn('innerHTML',script)
        self.assertIn("method:'GET'",script)
        self.assertIn("type=\"password\"",r.text)

if __name__=='__main__': unittest.main()
