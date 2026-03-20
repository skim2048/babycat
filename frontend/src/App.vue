<template>
  <div id="app">
    <RouterView />
    <Nav />
  </div>
</template>

<script setup>
import Nav from '@/components/Nav/Nav.vue'
</script>

<style>
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

html, body {
  width: 100%;
  height: 100%;
  overflow: hidden;
  overscroll-behavior: none;
  touch-action: none;
  background-color: #FFFBF5;
}

#app {
  width: 100%;
  height: 100%;
  overflow: hidden;
}
</style>