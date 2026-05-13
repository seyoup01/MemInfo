# Android PSS Memory Monitor

ADB로 연결된 Android 기기의 메모리 사용 현황을 실시간으로 모니터링하는 Windows PC 데스크톱 앱입니다.  
`adb shell dumpsys meminfo`의 **Total PSS by OOM adjustment** 데이터만 파싱하여 표시합니다.

---

## 실행 환경

| 항목 | 요구사항 |
|------|----------|
| OS | Windows 10/11 (64-bit) |
| Python | 3.10 이상 |
| ADB | Android SDK Platform-Tools (PATH 등록 또는 `assets/adb/` 폴더에 배치) |

---

## 설치 및 실행

### 1. 코드 받기
```powershell
git clone https://github.com/seyoup01/MemInfo.git
cd MemInfo
```

### 2. 가상환경 생성 (권장)
```powershell
python -m venv .venv
.venv\Scripts\activate
```

### 3. 패키지 설치
```powershell
pip install -r requirements.txt
```

### 4. 앱 실행
```powershell
python main.py
```

---

## ADB 설정

Android 기기 연결을 위해 ADB가 필요합니다.

**방법 A — Android SDK Platform-Tools를 PATH에 추가 (권장)**
1. https://developer.android.com/tools/releases/platform-tools 에서 다운로드
2. 압축 해제 후 `platform-tools` 폴더를 시스템 PATH에 추가

**방법 B — 앱 폴더에 직접 배치**
```
MemInfo/
└── assets/
    └── adb/
        ├── adb.exe
        └── AdbWinApi.dll
```

**Android 기기 설정**
- 개발자 옵션 활성화
- USB 디버깅 활성화
- USB 케이블로 PC 연결 후 "허용" 선택

---

## 기능

| 탭 | 기능 |
|----|------|
| 📋 Main View | ADJ 카테고리별 전체 프로세스 모니터링, 정렬(ADJ/Memory/Name/PID) |
| 🔍 Threshold Filter | 메모리 임계값 이상 프로세스만 필터링 |
| 📌 Process Select | 특정 프로세스를 선택해 집중 모니터링 |
| 📈 Chart | 선택 프로세스의 메모리 추이 실시간 차트 |

- 새로 나타난 프로세스: **초록색** 하이라이트
- 사라진 프로세스: **빨간색** 표시
- 메모리 변화량: ▲ / ▼ 표시
- CSV/JSON 내보내기
- 임계값 초과 알림 (Windows 토스트 + 알림음)
- 자동 재연결

---

## 테스트 실행

```powershell
python -m pytest tests/ -v
```

총 189개 테스트 (실제 ADB 기기 없이 MockAdbManager로 실행 가능)

---

## 프로젝트 구조

```
MemInfo/
├── main.py                  # 앱 진입점
├── requirements.txt
├── core/
│   ├── data_models.py       # ProcessEntry, ADJGroup, MemInfoSnapshot
│   ├── meminfo_parser.py    # dumpsys meminfo 파서
│   ├── adb_manager.py       # ADB 연결 + ReconnectWorker
│   ├── polling_worker.py    # QThread 기반 폴링
│   ├── history_manager.py   # SQLite 히스토리
│   └── alert_manager.py     # 임계값 알림
├── ui/
│   ├── main_window.py       # 메인 윈도우
│   ├── main_view.py         # 메인 모니터링 뷰
│   ├── threshold_view.py    # 임계값 필터 뷰
│   ├── selection_view.py    # 프로세스 선택 뷰
│   ├── chart_view.py        # 실시간 차트 (pyqtgraph)
│   ├── alert_log_panel.py   # 알림 로그 패널
│   ├── toolbar.py           # 툴바
│   └── status_bar.py        # 상태바
├── utils/
│   ├── sorter.py            # 정렬 로직
│   ├── settings.py          # JSON 설정 관리
│   └── exporter.py          # CSV/JSON 내보내기
└── tests/                   # pytest 테스트 (STEP 1~10 + 통합)
```
