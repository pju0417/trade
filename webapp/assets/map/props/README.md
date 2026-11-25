# Tripo 지형·도시 모델을 넣는 폴더

제작 프롬프트와 내보내기 기준은 [tripo-brief.md](../tripo-brief.md)에 있습니다.

우선 제작할 파일:

- `mountain-ridge.glb` — 산맥
- `coastal-cliff.glb` — 해안 절벽
- `old-town-block.glb` — 19세기 구시가지

추가 제작할 파일:

- `wheat-farm.glb` — 농경지
- `tropical-grove.glb` — 열대 숲

파일을 넣은 뒤 `../layout.json`의 `props` 배열에 모델 배치를 등록합니다.

```json
{"model":"mountain-ridge","position":[1100,440],"size":18,"rotation":0.4}
```

`model`은 확장자를 제외한 파일명입니다. 한 모델을 여러 좌표에 등록해 재사용할
수 있습니다. 파일을 아직 만들지 않은 현재 버전은 기본 지형으로 동작합니다.
