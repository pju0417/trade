# Tripo 3D로 지도 모델 만들기

지도의 항구·배·산업 건물은 지금 코드로 만든 임시 모델이다. Tripo 3D Pro로 만든 GLB로 바꿔 갈 때 쓰는 설정과 프롬프트다.

## 설정

- Smart Low Poly 켜기, **GLB**로 내보내기
- 면 수 목표: 크레인·정유 시설·사일로 3,000~5,000 / 창고·탱크·등대·산업 건물 1,500~3,000 / 배 2,000~4,000 / 집 500~1,000
- 텍스처 1K(집은 512)
- 나무는 Tripo로 만들지 않는다(수천 그루를 인스턴싱하는 코드 나무가 가볍다). 굳이 만들면 500면 이하
- 화풍 통일: 첫 모델이 마음에 들면 렌더 이미지를 저장해 두고, 이후엔 이미지→3D로 같은 화풍을 만든다
- 시험: 데모(`index.html`)의 "Tripo 모델(GLB) 불러오기"를 누르거나 GLB를 지도에 끌어다 놓으면 가장 가까운 항구의 등대 자리에 놓인다

## Negative prompt (공통)

```
realistic, photorealistic, high detail noise, text, logo, people, ground plane, terrain, multiple objects
```

## 프롬프트

모든 프롬프트 끝에 같은 스타일 문구가 붙어 있다(화풍을 맞추기 위해).

### 항구 (나라 대표 산업에 따라 모양이 다름)

**컨테이너 크레인 (기계·전자제품 항구)**
```
a ship-to-shore gantry container crane, orange steel frame, four legs, long horizontal boom, stylized low poly game asset, miniature diorama style, clean simple shapes, soft hand-painted texture, warm pastel colors, strategy game building, single object, centered, no ground, no base, no background
```

**창고**
```
a small port warehouse with a gabled blue-gray metal roof, cream walls, large loading doors, stylized low poly game asset, miniature diorama style, clean simple shapes, soft hand-painted texture, warm pastel colors, strategy game building, single object, centered, no ground, no base, no background
```

**컨테이너 더미**
```
a neat stack of colorful shipping containers, three levels high, red blue green yellow, stylized low poly game asset, miniature diorama style, clean simple shapes, soft hand-painted texture, warm pastel colors, strategy game building, single object, centered, no ground, no base, no background
```

**석유 저장탱크 (연료 항구)**
```
a cluster of four round white oil storage tanks with pipes and small stairs, stylized low poly game asset, miniature diorama style, clean simple shapes, soft hand-painted texture, warm pastel colors, strategy game building, single object, centered, no ground, no base, no background
```

**정유 시설 (연료 항구)**
```
a small oil refinery unit with tall gray distillation towers, red stripes, pipe racks and a flare stack, stylized low poly game asset, miniature diorama style, clean simple shapes, soft hand-painted texture, warm pastel colors, strategy game building, single object, centered, no ground, no base, no background
```

**철광석 야적장 (광물 항구)**
```
a pile of reddish-brown iron ore with a yellow conveyor belt and a ship loader, stylized low poly game asset, miniature diorama style, clean simple shapes, soft hand-painted texture, warm pastel colors, strategy game building, single object, centered, no ground, no base, no background
```

**곡물 사일로 (밀 항구)**
```
a group of tall cream grain silos with conical roofs connected by a conveyor gallery, stylized low poly game asset, miniature diorama style, clean simple shapes, soft hand-painted texture, warm pastel colors, strategy game building, single object, centered, no ground, no base, no background
```

**냉장 창고 (바나나 항구)**
```
a white refrigerated fruit warehouse with a green roof and stacks of yellow banana crates, stylized low poly game asset, miniature diorama style, clean simple shapes, soft hand-painted texture, warm pastel colors, strategy game building, single object, centered, no ground, no base, no background
```

**등대 (Tripo 모델 시험 자리)**
```
a white lighthouse with red stripes and a red conical roof on a small stone base, stylized low poly game asset, miniature diorama style, clean simple shapes, soft hand-painted texture, warm pastel colors, strategy game building, single object, centered, no ground, no base, no background
```

### 배

**컨테이너선**
```
a container cargo ship loaded with colorful containers, dark navy hull, white bridge at the stern, stylized low poly game asset, miniature diorama style, clean simple shapes, soft hand-painted texture, warm pastel colors, strategy game building, single object, centered, no ground, no base, no background
```

**유조선**
```
an oil tanker ship with a dark red hull, flat deck with pipes, white bridge at the stern, stylized low poly game asset, miniature diorama style, clean simple shapes, soft hand-painted texture, warm pastel colors, strategy game building, single object, centered, no ground, no base, no background
```

**벌크선 (광물·밀)**
```
a bulk carrier ship with a dark green hull, cargo hatches on deck, white bridge at the stern, stylized low poly game asset, miniature diorama style, clean simple shapes, soft hand-painted texture, warm pastel colors, strategy game building, single object, centered, no ground, no base, no background
```

**냉장선 (바나나)**
```
a white refrigerated cargo ship with small cranes on deck, white bridge at the stern, stylized low poly game asset, miniature diorama style, clean simple shapes, soft hand-painted texture, warm pastel colors, strategy game building, single object, centered, no ground, no base, no background
```

### 산업 건물 (레벨이 오르면 늘어나는 것)

**기계 공장 (기계)**
```
a small machine factory with a sawtooth roof, gray walls and a tall red and white chimney, stylized low poly game asset, miniature diorama style, clean simple shapes, soft hand-painted texture, warm pastel colors, strategy game building, single object, centered, no ground, no base, no background
```

**전자 회사 빌딩 (전자제품)**
```
a modern glass office tower with blue windows and a small rooftop antenna, stylized low poly game asset, miniature diorama style, clean simple shapes, soft hand-painted texture, warm pastel colors, strategy game building, single object, centered, no ground, no base, no background
```

**석유 펌프 (연료)**
```
an oil pumpjack with a red horsehead beam next to a small red storage tank, stylized low poly game asset, miniature diorama style, clean simple shapes, soft hand-painted texture, warm pastel colors, strategy game building, single object, centered, no ground, no base, no background
```

**광산 (광물)**
```
a wooden mine headframe tower with a winding wheel next to a pile of red ore, stylized low poly game asset, miniature diorama style, clean simple shapes, soft hand-painted texture, warm pastel colors, strategy game building, single object, centered, no ground, no base, no background
```

**농장 (밀)**
```
a red farm barn with a dark roof next to a tall grain silo, stylized low poly game asset, miniature diorama style, clean simple shapes, soft hand-painted texture, warm pastel colors, strategy game building, single object, centered, no ground, no base, no background
```

**바나나 농장 (바나나)**
```
a small banana plantation with three banana trees and stacked yellow banana crates, stylized low poly game asset, miniature diorama style, clean simple shapes, soft hand-painted texture, warm pastel colors, strategy game building, single object, centered, no ground, no base, no background
```

### 마을

**주택**
```
a small two-story house with an orange tiled roof and cream walls, stylized low poly game asset, miniature diorama style, clean simple shapes, soft hand-painted texture, warm pastel colors, strategy game building, single object, centered, no ground, no base, no background
```

**아파트**
```
a small white apartment block, four floors, flat roof, stylized low poly game asset, miniature diorama style, clean simple shapes, soft hand-painted texture, warm pastel colors, strategy game building, single object, centered, no ground, no base, no background
```
