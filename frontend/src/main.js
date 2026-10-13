import "./main.scss";
import * as bootstrap from "bootstrap";

window.bootstrap = bootstrap;

// Registration guest rows: show filled rows plus one empty row, and an "Add guest" button for more.
for (const container of document.querySelectorAll("[data-guest-rows]")) {
  const rows = [...container.querySelectorAll("[data-guest-row]")];
  const button = container.querySelector("[data-add-guest]");
  // Checkboxes always have a value ("on"), so only text inputs decide whether a row is empty.
  const isEmpty = (row) =>
    [...row.querySelectorAll('input:not([type="checkbox"])')].every((input) => !input.value.trim());
  let shownEmpty = false;
  for (const row of rows) {
    if (isEmpty(row)) {
      row.hidden = shownEmpty;
      shownEmpty = true;
    }
  }
  const refresh = () => {
    button.hidden = !rows.some((row) => row.hidden);
  };
  button.addEventListener("click", () => {
    const next = rows.find((row) => row.hidden);
    if (next) {
      next.hidden = false;
      next.querySelector("input")?.focus();
    }
    refresh();
  });
  refresh();
}
