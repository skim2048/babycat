// Flat dotted-key catalogue. Each entry: { en, ko }.
// Mirrors babycat-web's pattern.

export const messages = {
  // ── App-level ────────────────────────────────────────────────────────────
  'app.sseConnected':    { en: '● Live',          ko: '● 실시간' },
  'app.sseDisconnected': { en: '○ Disconnected',  ko: '○ 연결 끊김' },

  // ── Menu (hamburger) ─────────────────────────────────────────────────────
  'menu.aria':       { en: 'Open menu',     ko: '메뉴 열기' },
  'menu.language':   { en: 'Switch Language', ko: '언어 전환' },
  'menu.theme':      { en: 'Change Theme',    ko: '테마 변경' },

  // ── Dashboard cards ──────────────────────────────────────────────────────
  'dashboard.uri':      { en: 'STREAM URI',     ko: '송출 URI' },
  'dashboard.status':   { en: 'STREAM STATUS',  ko: '송출 상태' },
  'dashboard.params':   { en: 'STREAM PARAMS',  ko: '송출 파라미터' },
  'dashboard.statusOn': { en: 'Streaming',      ko: '송출 중' },
  'dashboard.statusOff':{ en: 'Stopped',        ko: '정지' },
  'dashboard.idle':     { en: 'It will appear here when streaming starts.', ko: '송출이 시작되면 여기에 표시됩니다.' },
  'dashboard.loading':  { en: 'Loading settings…', ko: '설정 로드 중…' },
  'dashboard.user':     { en: 'User',     ko: '아이디' },
  'dashboard.password': { en: 'Password', ko: '비밀번호' },
  'dashboard.show':     { en: 'Show',     ko: '보기' },
  'dashboard.hide':     { en: 'Hide',     ko: '숨김' },

  // ── Mode / params labels ─────────────────────────────────────────────────
  'mode.shuffleOn':  { en: 'Shuffle on',  ko: '셔플 켜짐' },
  'mode.shuffleOff': { en: 'Shuffle off', ko: '셔플 꺼짐' },
  'mode.repeatOff':  { en: 'Repeat off',  ko: '반복 꺼짐' },
  'mode.repeatAll':  { en: 'Repeat all',  ko: '반복 전체' },
  'mode.repeatOne':  { en: 'Repeat one',  ko: '반복 한 곡' },

  'params.resolution': { en: 'Resolution', ko: '해상도' },
  'params.fps':        { en: 'Frame rate', ko: '프레임' },
  'params.bitrate':    { en: 'Bitrate',    ko: '비트레이트' },
  'params.audio':      { en: 'Audio',      ko: '오디오' },
  'params.audioKeep':  { en: 'Audio kept',     ko: '음성 유지' },
  'params.audioDrop':  { en: 'Audio stripped', ko: '음성 제거' },
  'params.fpsUnit':    { en: 'fps',  ko: 'fps' },
  'params.mbps':       { en: 'Mbps', ko: 'Mbps' },

  // ── File tree pane ───────────────────────────────────────────────────────
  'tree.title':       { en: 'Files',          ko: '파일 트리' },
  'tree.search':      { en: 'Search files',   ko: '파일명 검색' },
  'tree.addTitle':    { en: 'Add checked files to the stream queue', ko: '체크된 파일을 송출 목록에 추가' },
  'tree.addAria':     { en: 'Add to stream queue', ko: '송출 목록에 추가' },
  'tree.noMatch':     { en: 'No matching files.', ko: '일치하는 파일이 없습니다.' },

  // ── Playlist pane ────────────────────────────────────────────────────────
  'playlist.title':       { en: 'Stream Queue',     ko: '송출 목록' },
  'playlist.search':      { en: 'Search files',     ko: '파일명 검색' },
  'playlist.removeTitle': { en: 'Remove checked items from the stream queue', ko: '체크된 항목을 송출 목록에서 제거' },
  'playlist.removeAria':  { en: 'Remove from stream queue', ko: '송출 목록에서 제거' },
  'playlist.noMatch':     { en: 'No matching items.',   ko: '일치하는 항목이 없습니다.' },
  'playlist.empty':       { en: 'The stream queue is empty.', ko: '송출 목록이 비어 있습니다.' },

  // ── Bottom controls ──────────────────────────────────────────────────────
  'controls.play':        { en: 'Stream',       ko: '송출' },
  'controls.stop':        { en: 'Stop',         ko: '정지' },
  'controls.shuffleOn':   { en: 'Turn shuffle off', ko: '셔플 끄기' },
  'controls.shuffleOff':  { en: 'Turn shuffle on',  ko: '셔플 켜기' },
  'controls.shuffleAria': { en: 'Shuffle',      ko: '셔플' },
  'controls.repeatAria':  { en: 'Repeat',       ko: '반복' },
  'controls.repeatOff':   { en: 'Repeat off',   ko: '반복 끄기' },
  'controls.repeatAll':   { en: 'Repeat all',   ko: '전체 반복' },
  'controls.repeatOne':   { en: 'Repeat one',   ko: '단일 반복' },

  // ── Settings modal ───────────────────────────────────────────────────────
  'settings.title':    { en: 'RTSP Server Settings', ko: 'RTSP 서버 설정' },
  'settings.aria':     { en: 'RTSP Server Settings', ko: 'RTSP 서버 설정' },
  'settings.banner':   { en: 'Settings cannot be changed while streaming. Please stop first.',
                         ko: '송출 중에는 설정을 변경할 수 없습니다. 먼저 정지해 주십시오.' },
  'settings.user':     { en: 'User',     ko: '아이디' },
  'settings.password': { en: 'Password', ko: '비밀번호' },
  'settings.port':     { en: 'Port',     ko: '포트' },
  'settings.path':     { en: 'Path',     ko: '경로' },
  'settings.resolution':{ en: 'Resolution', ko: '해상도' },
  'settings.fps':      { en: 'Frame rate', ko: '프레임레이트' },
  'settings.bitrate':  { en: 'Bitrate',  ko: '비트레이트' },
  'settings.audio':    { en: 'Audio',    ko: '오디오' },
  'settings.audioKeep':{ en: 'Keep',     ko: '유지' },
  'settings.audioDrop':{ en: 'Strip',    ko: '제거' },
  'settings.reset':    { en: 'Revert',   ko: '되돌리기' },
  'settings.save':     { en: 'Save',     ko: '저장' },
  'settings.close':    { en: 'Close',    ko: '닫기' },
  'settings.errPort':  { en: 'Port must be between 1 and 65535.', ko: '포트는 1–65535 사이여야 합니다.' },
  'settings.errPath':  { en: 'Path may only contain letters, digits, -, _, /.', ko: '경로는 영문·숫자·-·_·/만 사용할 수 있습니다.' },
  'settings.errUser':  { en: 'User must be 1–64 characters.',  ko: '아이디는 1–64자여야 합니다.' },
  'settings.errPass':  { en: 'Password must be 1–128 characters.', ko: '비밀번호는 1–128자여야 합니다.' },

  // ── Common ───────────────────────────────────────────────────────────────
  'common.selectAll':       { en: 'All',         ko: '전체' },
  'common.loading':         { en: 'Loading…',    ko: '불러오는 중…' },
  'common.disabledPlaying': { en: 'Cannot change while streaming', ko: '송출 중에는 변경할 수 없습니다' },
}
