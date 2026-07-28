# 8. 변경 관리 프로세스 (Change Management Process)

1인 프로젝트 특성을 고려하여, 의사결정 지연을 방지하고자 별도의 변경관리위원회(CCB, Configuration Control Board)는 운영하지 않는다. 본 문서 및 시스템 산출물의 모든 변경 이력은 Git 커밋(Commit)을 통해 단일 진실 공급원(SSOT)으로 추적되며, 릴리스가 확정된 버전은 저장소의 태그(Tag) 기능을 활용해 베이스라인(Baseline)으로 설정하고 형상을 통제한다.