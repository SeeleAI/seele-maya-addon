import hashlib, os, sys, tempfile, unittest, uuid
from datetime import datetime, timedelta, timezone
sys.path.insert(0,os.path.abspath('SeeleMaya/scripts'))
from seele_maya.formats import FORMAT_SPECS, FORBIDDEN_FORMATS, format_spec, validate_registry
from seele_maya.contract.validator import validate_manifest, ContractError
from seele_maya.contract.dependencies import validate_obj_closure

def manifest(format_name,files):
    now=datetime.now(timezone.utc)
    return {'version':'dcc-transfer.v1','transferId':str(uuid.uuid4()),'receiverId':'r','target':{'dcc':'maya','format':format_name},'entryFileId':'model','createdAt':now.isoformat(),'expiresAt':(now+timedelta(minutes=10)).isoformat(),'files':files}

def file_spec(id_,kind,format_name,path,data=b''):
    content_types={'fbx':'application/octet-stream','obj':'text/plain','abc':'application/octet-stream','mtl':'text/plain','png':'image/png'}
    return {'id':id_,'kind':kind,'format':format_name,'contentType':content_types.get(format_name,'application/octet-stream'),'path':path,'downloadUrl':'https://static.seeles.ai/'+path,'sizeBytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}

class TestFormatRegistry(unittest.TestCase):
    def test_registry(self):
        self.assertTrue(validate_registry()); self.assertEqual('.usda',format_spec('usda')['extension'])
        self.assertEqual({'fbx','obj','abc','dae','usd','usda','usdc'},set(FORMAT_SPECS))
        self.assertIn('gltf',FORBIDDEN_FORMATS)
    def test_p0_contracts(self):
        for name in ('fbx','obj','abc'):
            data=b'x'; self.assertTrue(validate_manifest(manifest(name,[file_spec('model','MODEL',name,'asset.'+name,data)]),'r'))
    def test_forbidden_format(self):
        data=b'x'
        with self.assertRaises(ContractError) as caught: validate_manifest(manifest('gltf',[file_spec('model','MODEL','gltf','asset.gltf',data)]),'r')
        self.assertEqual('UNSUPPORTED_FORMAT',caught.exception.code)
    def test_abc_rejects_sidecar(self):
        data=b'x'; files=[file_spec('model','MODEL','abc','asset.abc',data),file_spec('tex','TEXTURE','png','a.png',data)]
        with self.assertRaises(ContractError) as caught: validate_manifest(manifest('abc',files),'r')
        self.assertEqual('DEPENDENCY_UNSUPPORTED',caught.exception.code)

class TestObjDependencies(unittest.TestCase):
    def test_obj_mtl_texture_closure(self):
        obj=b'mtllib materials/a.mtl\n'; mtl=b'map_Kd ../textures/a.png\n'; tex=b'png'
        files=[file_spec('model','MODEL','obj','model.obj',obj),file_spec('mtl','AUXILIARY','mtl','materials/a.mtl',mtl),file_spec('tex','TEXTURE','png','textures/a.png',tex)]; value=manifest('obj',files); validate_manifest(value,'r')
        with tempfile.TemporaryDirectory() as root:
            for spec,data in zip(files,(obj,mtl,tex)):
                path=os.path.join(root,'files',*spec['path'].split('/')); os.makedirs(os.path.dirname(path),exist_ok=True)
                with open(path,'wb') as stream: stream.write(data)
            closure=validate_obj_closure(root,value); self.assertEqual(['materials/a.mtl'],closure['materials']); self.assertEqual(['textures/a.png'],closure['textures'])
    def test_obj_missing_mtl_warns(self):
        obj=b'mtllib absent.mtl\n'; value=manifest('obj',[file_spec('model','MODEL','obj','model.obj',obj)]); validate_manifest(value,'r')
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root,'files'))
            with open(os.path.join(root,'files','model.obj'),'wb') as stream: stream.write(obj)
            result=validate_obj_closure(root,value)
            self.assertEqual('OBJ_MTL_NOT_PROVIDED',result['warnings'][0]['code'])
    def test_obj_percent_encoded_dependency_rejected(self):
        obj=b'mtllib %2e%2e/escape.mtl\n'; value=manifest('obj',[file_spec('model','MODEL','obj','model.obj',obj)]); validate_manifest(value,'r')
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root,'files'))
            with open(os.path.join(root,'files','model.obj'),'wb') as stream: stream.write(obj)
            with self.assertRaises(ContractError) as caught: validate_obj_closure(root,value)
            self.assertEqual('PATH_UNSAFE',caught.exception.code)
