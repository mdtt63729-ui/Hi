from pathlib import Path
from zipfile import ZipFile
from app.services.zip_service import ZipService
import pytest

def test_valid_zip(tmp_path):
 z=tmp_path/'a.zip'
 with ZipFile(z,'w') as f:f.writestr('project/app/build.gradle','x')
 out=tmp_path/'out'; ZipService().extract(z,out); assert (out/'app/build.gradle').exists()
def test_traversal(tmp_path):
 z=tmp_path/'bad.zip'
 with ZipFile(z,'w') as f:f.writestr('../evil','x')
 with pytest.raises(Exception): ZipService().validate(z)
