<template>
  <div :class="$style.iconGroup">
    <div :class="$style.rectangle" />
    <div :class="$style.homeIcons">
      <img :class="$style.iconLightLine" src="/icons/Home/Light_Line.svg" alt="라이트" />
      <div :class="$style.div">라이트</div>
      <img :class="$style.iconTemperature" src="/icons/Home/Temperature.svg" alt="온도조절" />
      <div :class="$style.div2">온도조절</div>
      <img :class="$style.iconMicLine" src="/icons/Home/Mic_Line.svg" alt="대화하기" />
      <div :class="$style.div3">대화하기</div>
    </div>
  </div>
</template>

<style module>
@font-face {
  font-family: 'Malang';
  src: url('@/assets/Fonts/Malang_Regular.ttf') format('truetype');
}

.iconGroup {
  width: 100%;
  height: 531px;
  position: relative;
  text-align: center;
  font-size: 10px;
  color: #000;
  font-family: 'Malang', sans-serif;
}
.rectangle {
  position: absolute;
  top: 0px;
  left: 0px;
  background-color: #f5f0e9;
  width: 100%;
  height: 531px;
}
.homeIcons {
  position: absolute;
  top: 16px;
  left: 20px;
  right: 20px;
  border-radius: 10px;
  background-color: #fffbf5;
  height: 176px;
  overflow: hidden;
}
.iconLightLine {
  position: absolute;
  top: 29px;
  left: 35px;
  width: 25px;
  height: 25px;
}
.div {
  position: absolute;
  top: 57px;
  left: 34px;
  display: inline-block;
  width: 29px;
  height: 10px;
}
.div2 {
  position: absolute;
  top: 57px;
  left: 105px;
  display: inline-block;
  width: 34px;
  height: 10px;
}
.div3 {
  position: absolute;
  top: 57px;
  left: 179px;
  display: inline-block;
  width: 37px;
  height: 10px;
}
.iconTemperature {
  position: absolute;
  top: 29px;
  left: 110px;
  width: 25px;
  height: 25px;
}
.iconMicLine {
  position: absolute;
  top: 29px;
  left: 185px;
  width: 25px;
  height: 25px;
}
</style>
