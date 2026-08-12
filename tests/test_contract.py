import sys, os, unittest, uuid
from datetime import datetime, timedelta, timezone
sys.path.insert(0, os.path.abspath('SeeleMaya/scripts'))
from seele_maya.contract.validator import validate_manifest, ContractError
class TestContract(unittest.TestCase):
 def test_valid(self):
  now=datetime.now(timezone.utc); m={'version':'dcc-transfer.v1','transferId':str(uuid.uuid4()),'receiverId':'r','target':{'dcc':'maya','format':'fbx'},'entryFileId':'m','createdAt':now.isoformat(),'expiresAt':(now+timedelta(minutes=10)).isoformat(),'files':[{'id':'m','kind':'MODEL','format':'fbx','path':'assets/a.fbx','sizeBytes':0,'sha256':'0'*64}]}
  self.assertTrue(validate_manifest(m,'r'))
 def test_traversal(self):
  now=datetime.now(timezone.utc); m={'version':'dcc-transfer.v1','transferId':str(uuid.uuid4()),'receiverId':'r','target':{'dcc':'maya','format':'fbx'},'entryFileId':'m','createdAt':now.isoformat(),'expiresAt':(now+timedelta(minutes=10)).isoformat(),'files':[{'id':'m','kind':'MODEL','format':'fbx','path':'../a.fbx','sizeBytes':0,'sha256':'0'*64}]}
  with self.assertRaises(ContractError): validate_manifest(m,'r')
 def test_expired(self):
  now=datetime.now(timezone.utc); m={'version':'dcc-transfer.v1','transferId':str(uuid.uuid4()),'receiverId':'r','target':{'dcc':'maya','format':'fbx'},'entryFileId':'m','createdAt':(now-timedelta(minutes=20)).isoformat(),'expiresAt':(now-timedelta(minutes=10)).isoformat(),'files':[{'id':'m','kind':'MODEL','format':'fbx','path':'a.fbx','sizeBytes':0,'sha256':'0'*64}]}
  with self.assertRaises(ContractError) as caught: validate_manifest(m,'r')
  self.assertEqual('TRANSFER_EXPIRED',caught.exception.code)
 def test_invalid_limits(self):
  now=datetime.now(timezone.utc); m={'version':'dcc-transfer.v1','transferId':str(uuid.uuid4()),'receiverId':'r','target':{'dcc':'maya','format':'fbx'},'entryFileId':'m','createdAt':now.isoformat(),'expiresAt':(now+timedelta(minutes=10)).isoformat(),'limits':{'maxFiles':'bad'},'files':[{'id':'m','kind':'MODEL','format':'fbx','path':'a.fbx','sizeBytes':0,'sha256':'0'*64}]}
  with self.assertRaises(ContractError) as caught: validate_manifest(m,'r')
  self.assertEqual('MANIFEST_INVALID',caught.exception.code)
