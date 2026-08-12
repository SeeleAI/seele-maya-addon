import sys, os, unittest, uuid
sys.path.insert(0, os.path.abspath('SeeleMaya/scripts'))
from seele_maya.contract.validator import validate_manifest, ContractError
class TestContract(unittest.TestCase):
 def test_valid(self):
  m={'version':'dcc-transfer.v1','transferId':str(uuid.uuid4()),'receiverId':'r','target':{'dcc':'maya','format':'fbx'},'entryFileId':'m','files':[{'id':'m','kind':'MODEL','format':'fbx','path':'assets/a.fbx'}]}
  self.assertTrue(validate_manifest(m,'r'))
 def test_traversal(self):
  m={'version':'dcc-transfer.v1','transferId':str(uuid.uuid4()),'receiverId':'r','target':{'dcc':'maya','format':'fbx'},'entryFileId':'m','files':[{'id':'m','kind':'MODEL','format':'fbx','path':'../a.fbx'}]}
  with self.assertRaises(ContractError): validate_manifest(m,'r')
