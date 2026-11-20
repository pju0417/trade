# Firebase 서버 설정 안내

학생이 자기 기기(태블릿·크롬북)로 들어오려면 Firebase 서버가 필요하다.

- **서버 1개 = Firebase 프로젝트 1개**다. 무료 요금제(Spark)에서는 프로젝트마다 동시 접속이 100개까지이고, 이 숫자는 늘릴 수 없다.
- 접속 1개는 기기 1대(또는 브라우저 탭 1개)다. 한 반이 교사 화면 1개와 학생 30명이면 31개다.
- 그래서 정원은 여유를 두고 **90명**으로 잡는다. 동시에 여러 학교가 쓰면 서버를 늘린다.

## 1. 서버 하나 만들기 (서버 수만큼 반복)

Firebase 콘솔의 메뉴 이름은 바뀔 수 있다. 아래는 2026년 11월 공식 문서 기준이다.

1. https://console.firebase.google.com 에 Google 계정으로 들어간다.
2. **프로젝트 만들기**: 이름 예) `trade-game-1`. Google 애널리틱스는 꺼도 된다.
3. 왼쪽 메뉴 **Databases & Storage → Realtime Database → 데이터베이스 만들기(Create database)**.
   - **위치:** 싱가포르(`asia-southeast1`)가 한국에서 가장 가깝다.
   - **보안 규칙 시작 모드:** **잠금 모드(Locked mode)**를 고른다. 테스트 모드는 기간이 지나면 막힌다.
4. Realtime Database 화면의 **규칙(Rules)** 탭에 아래 규칙을 그대로 붙여 넣고 **게시(Publish)**를 누른다.

   ```json
   {
     "rules": {
       "rooms": {
         "$room": { ".read": true, ".write": true }
       },
       "presence": {
         ".read": true,
         "$id": { ".write": true }
       }
     }
   }
   ```

   - `rooms`: 방마다 게임 상태와 학생 행동이 오가는 곳이다.
   - `presence`: 지금 접속한 기기 목록이다. 첫 화면의 "지금 접속 ○명"이 여기서 나온다.
   - 나머지 경로는 읽기·쓰기가 막힌다.
5. **프로젝트 설정(톱니바퀴) → 일반 → 내 앱 → 웹(`</>`) 아이콘**을 누른다.
   - 앱 이름(예: `trade-web`)을 넣고 등록한다. Firebase 호스팅은 체크하지 않아도 된다.
   - 화면에 나오는 `firebaseConfig = { ... }`의 내용을 복사한다.
6. 복사한 설정에 `databaseURL`이 있는지 확인한다. 없으면 Realtime Database 화면 위쪽의 주소를 직접 넣는다.
   - 싱가포르: `https://<이름>-default-rtdb.asia-southeast1.firebasedatabase.app`
   - 미국(`us-central1`): `https://<이름>-default-rtdb.firebaseio.com`

## 2. 웹앱에 서버 넣기

`webapp/js/config.js`의 `SERVERS`에 서버마다 한 줄씩 넣는다. 순서대로 1서버, 2서버, …가 된다.

```js
export const SERVERS = [
  { name: '1서버', capacity: 90, firebase: {
      apiKey: '...', authDomain: 'trade-game-1.firebaseapp.com',
      databaseURL: 'https://trade-game-1-default-rtdb.asia-southeast1.firebasedatabase.app',
      projectId: 'trade-game-1', appId: '...' } },
  { name: '2서버', capacity: 90, firebase: { /* 두 번째 프로젝트의 설정 */ } },
];
```

- 방 코드 앞자리가 서버 번호다(예: `2-K7QPM-1`은 2서버의 K7QPM 수업 1번 방). 학생은 방 코드만 넣으면 그 서버로 연결된다.
- **이미 쓰고 있는 서버의 순서를 바꾸거나 지우지 않는다.** 방 코드의 서버 번호가 달라져 진행 중인 수업에 들어갈 수 없게 된다. 새 서버는 맨 뒤에 붙인다.
- 웹 설정값(`apiKey` 등)은 비밀번호가 아니다. 브라우저에 그대로 보이는 공개 식별자이고, 보안은 위의 규칙이 맡는다. 공개 저장소에 올려도 된다.

## 3. 웹앱을 인터넷에 올리기

학생 기기에서 열 주소가 필요하다. 저장소 `pju0417/trade`를 그대로 쓰는 방법:

1. GitHub 저장소 → **Settings → Pages**.
2. Source를 **Deploy from a branch**, 브랜치를 `main`, 폴더를 `/ (root)`로 두고 저장한다.
3. 몇 분 뒤 다음 주소로 열린다.
   - 교사: `https://pju0417.github.io/trade/webapp/host.html`
   - 학생: `https://pju0417.github.io/trade/webapp/student.html`
   - 첫 화면(서버 접속 현황): `https://pju0417.github.io/trade/webapp/`

교사 화면과 학생 화면은 같은 주소(같은 `config.js`)에서 열어야 서버 목록이 맞는다.

## 4. 연결 확인

1. 교사 화면을 연다. "서버" 표에 서버마다 "지금 접속 ○명"이 숫자로 나오면 연결된 것이다. `?`면 아래 "문제 해결"을 본다.
2. 방 1개로 수업을 만들고, 다른 기기(휴대폰도 됨)에서 학생 화면에 방 코드·나라·접속 번호를 넣어 들어가 본다.
3. 교사 화면의 "접속" 칸 숫자가 올라가면 끝이다.

## 5. 운영 메모

- **사용량:** 무료 요금제는 저장 1GB, 내려받기 월 10GB다. 수업이 끝나면 교사 화면의 **수업 끝내기**를 눌러 서버에서 방 자료를 지운다. 이 컴퓨터의 기록은 남아 다시 볼 수 있다. 한 수업이 쓰는 양은 아직 재 보지 않았다. 처음 몇 번은 콘솔의 Realtime Database → **사용량(Usage)** 탭을 확인한다.
- **보안 수준:** 방 코드를 아는 사람은 그 방 자료를 읽고 쓸 수 있다.
  - 그래서 학생 이름 등 개인정보는 넣지 않는다. 화면에도 나라 이름만 쓴다.
  - 학생 접속 번호는 서버에 저장하지 않는다. 교사 화면이 행동마다 번호를 확인한다.
  - 다만 학생 행동은 처리되기 전까지 잠깐 서버에 남는다.
- **정원:** 정원(`capacity`)은 교사 화면이 "자리 남았나"를 판단하는 기준일 뿐이다. 실제 한도(100)를 넘으면 Firebase가 새 접속을 받지 않는다.
- **교사 컴퓨터:** 모든 방의 게임은 교사 화면에서 돈다. 수업 중에는 교사 화면을 닫거나 절전되지 않게 한다. 닫혔다면 같은 컴퓨터·브라우저에서 다시 열고 **이어하기**를 누른다.

## 6. 문제 해결

| 증상 | 확인할 것 |
| --- | --- |
| 서버 표의 접속 인원이 `?` | `databaseURL` 오타, 규칙을 게시했는지(`presence`의 `.read: true`) |
| 학생: "이 방 코드의 서버가 설정되어 있지 않아요" | 학생이 교사와 다른 주소(다른 `config.js`)로 열었는지 |
| 학생: "선생님 화면의 응답이 없어요" | 교사 화면이 열려 있는지, 교사 컴퓨터가 절전 상태인지 |
| 학생: "방 코드, 나라 또는 접속 번호가 맞지 않아요" | 나라를 바꿔 골랐는지, 다른 방의 번호인지 |
