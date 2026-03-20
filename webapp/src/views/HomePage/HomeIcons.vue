<template>
  <div class="icon-group">
    <div class="icon-card">
      <div class="icon-item">
        <img src="/icons/Home/Light_Line.svg" alt="라이트" />
        <span>라이트</span>
      </div>
      <div class="icon-item">
        <img src="/icons/Home/Temperature.svg" alt="온도조절" />
        <span>온도조절</span>
      </div>
      <div class="icon-item">
        <img src="/icons/Home/Mic_Line.svg" alt="대화하기" />
        <span>대화하기</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
@font-face {
  font-family: 'Malang';
  src: url('@/assets/Fonts/Malang_Regular.ttf') format('truetype');
}

.icon-group {
  flex: 1;
  background-color: #f5f0e9;
  padding: 16px;
  overflow: hidden;
}

.icon-card {
  display: flex;
  justify-content: space-around;
  align-items: center;
  background-color: #fffbf5;
  border-radius: 10px;
  padding: 16px;
  height: 80px;
}

.icon-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  font-size: 10px;
  font-family: 'Malang', sans-serif;
  color: #000;
}

.icon-item img {
  width: 25px;
  height: 25px;
}
</style>
