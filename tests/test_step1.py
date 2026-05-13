"""STEP 1 검증: 프로젝트 초기 구조 및 픽스처 확인"""
import os
import pytest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_requirements_exists():
    path = os.path.join(BASE, "requirements.txt")
    assert os.path.exists(path), "requirements.txt 파일이 없습니다"


def test_requirements_contains_packages():
    path = os.path.join(BASE, "requirements.txt")
    with open(path, encoding="utf-8") as f:
        content = f.read()
    for pkg in ["PyQt6", "pyqtgraph", "plyer", "pytest"]:
        assert pkg in content, f"requirements.txt에 {pkg}가 없습니다"


def test_sample_meminfo_exists():
    path = os.path.join(BASE, "tests", "fixtures", "sample_meminfo.txt")
    assert os.path.exists(path), "sample_meminfo.txt 파일이 없습니다"


def test_sample_meminfo_contains_target_section():
    path = os.path.join(BASE, "tests", "fixtures", "sample_meminfo.txt")
    with open(path, encoding="utf-8") as f:
        content = f.read()
    assert "Total PSS by OOM adjustment:" in content, \
        "샘플 파일에 'Total PSS by OOM adjustment:' 섹션이 없습니다"


def test_sample_meminfo_contains_other_sections():
    """파서 격리 테스트용: 다른 섹션도 파일에 존재해야 함"""
    path = os.path.join(BASE, "tests", "fixtures", "sample_meminfo.txt")
    with open(path, encoding="utf-8") as f:
        content = f.read()
    assert "Total PSS by process:" in content, \
        "격리 테스트용 'Total PSS by process:' 섹션이 없습니다"
    assert "Total PSS by category:" in content, \
        "격리 테스트용 'Total PSS by category:' 섹션이 없습니다"


def test_init_files_exist():
    """모든 패키지 디렉토리에 __init__.py가 존재하는지 확인"""
    packages = ["core", "ui", "utils", "tests"]
    for pkg in packages:
        path = os.path.join(BASE, pkg, "__init__.py")
        assert os.path.exists(path), f"{pkg}/__init__.py 파일이 없습니다"


def test_module_files_exist():
    """핵심 모듈 파일들이 존재하는지 확인"""
    files = [
        "core/adb_manager.py",
        "core/meminfo_parser.py",
        "core/data_models.py",
        "core/history_manager.py",
        "core/alert_manager.py",
        "ui/main_window.py",
        "ui/toolbar.py",
        "ui/main_view.py",
        "ui/threshold_view.py",
        "ui/selection_view.py",
        "ui/chart_view.py",
        "ui/alert_log_panel.py",
        "ui/status_bar.py",
        "utils/settings.py",
        "utils/exporter.py",
    ]
    for rel_path in files:
        full_path = os.path.join(BASE, rel_path)
        assert os.path.exists(full_path), f"{rel_path} 파일이 없습니다"


def test_main_py_exists_and_has_version():
    path = os.path.join(BASE, "main.py")
    assert os.path.exists(path), "main.py 파일이 없습니다"
    with open(path, encoding="utf-8") as f:
        content = f.read()
    assert "__version__" in content, "main.py에 __version__이 없습니다"
