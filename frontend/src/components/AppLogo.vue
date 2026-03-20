<template>
  <div :class="$style.head">
    <img :class="$style.logo" src="@/assets/Logo.svg" alt="Wally" />
  </div>
</template>

<style module>
.head {
  width: 100%;
  height: 60px;
  position: relative;
}
.logo {
  position: absolute;
  top: 12px;
  left: 17px;
  width: 68px;
  height: 37px;
}
</style>
