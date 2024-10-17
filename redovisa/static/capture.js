window.addEventListener("load", (event) => {
  const input = document.querySelector("input#receipts");
  const button = document.querySelector("button#no_capture");

  button.addEventListener("click", () => {
    input.removeAttribute("capture");
  });
});
