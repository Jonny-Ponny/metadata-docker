import { mount } from "svelte";
import "./app.css";
import App from "./App.svelte";

const target = document.getElementById("app");
if (!target) {
  throw new Error('Mount point "#app" is missing from index.html');
}

const app = mount(App, {
  target,
});

export default app;
