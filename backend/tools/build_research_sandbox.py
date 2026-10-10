"""Operator-only allowlisted Docker image build; no generated code is run at build time."""
import json
from pathlib import Path
import sys
import tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.research_agent.sandbox import Docker
from app.research_agent.sandbox_image import stage,TAG

if __name__=='__main__':
    docker=Docker('image-build')
    try:
        docker.call('pull','--platform','linux/amd64','python:3.12-slim',timeout=300)
        base=json.loads(docker.call('image','inspect','python:3.12-slim'))[0]['RepoDigests'][0]
        with tempfile.TemporaryDirectory(prefix='ledger-sandbox-build-') as directory:
            manifest=stage(directory)
            docker.call('build','--platform','linux/amd64','--build-arg','BASE='+base,
                        '--label','com.ledger.research.build='+manifest['sha256'],'-t',TAG,directory,timeout=600)
        print(json.dumps({'base':base,'image':docker.image(),'build':manifest},indent=2))
    finally:docker.close()
