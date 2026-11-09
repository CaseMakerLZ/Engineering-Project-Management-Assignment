"""发布前真实Docker检查，使用临时项目，不调用模型API或处理真实用户文件。"""
import tempfile
import argparse
from pathlib import Path
from tools.terminal.sandbox import ContainerExecutor, SandboxLimits
from tools.terminal.workspace import SandboxWorkspace, WorkspaceLimits


def main(image="python-agent-sandbox:1"):
    with tempfile.TemporaryDirectory(prefix="agent-deploy-verify-") as directory:
        root = Path(directory)
        workspace = SandboxWorkspace(root, WorkspaceLimits())
        executor = ContainerExecutor(workspace, SandboxLimits(image=image, timeout_seconds=30))
        try:
            executor.start()
            first = executor.run_command("python3", ["-c",
                "import os,socket; from pathlib import Path; "
                "from docx import Document; from openpyxl import Workbook; "
                "import numpy,pandas,matplotlib,PIL,pypdf,reportlab; "
                "assert os.getuid()==1000; "
                "assert not Path('/var/run/docker.sock').exists(); "
                "assert not Path('/etc/agent/python.toml').exists(); "
                "d=Document(); d.add_paragraph('deployment check'); d.save('check.docx'); "
                "w=Workbook(); w.active['A1']='ok'; w.save('check.xlsx'); "
                "Path('.venv').mkdir(); Path('.venv/marker').write_text('ok'); "
                "s=socket.socket(); s.settimeout(1); "
                "assert s.connect_ex(('1.1.1.1',80)) != 0"])
            if first.exit_code != 0:
                raise RuntimeError("容器内Office或隔离检查失败")
            second = executor.run_shell(
                "test -f .venv/marker && node --input-type=module "
                "-e \"import * as THREE from 'three'; console.log(new THREE.Scene().type)\"")
            if second.exit_code != 0:
                raise RuntimeError("容器跨命令状态或Three.js检查失败")
            if not (workspace.root / "check.docx").read_bytes().startswith(b"PK"):
                raise RuntimeError("DOCX产物检查失败")
            if (workspace.root / ".venv").exists():
                raise RuntimeError("临时依赖不应导出")
        finally:
            try:
                executor.close()
            finally:
                workspace.close()
    print("真实容器Office、Three.js、任务内复用及清理检查通过")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", default="python-agent-sandbox:1")
    main(parser.parse_args().image)
