function updateTotal() {
  var arr = document.getElementsByClassName("amount");
  var tot = 0;
  for (var i = 0; i < arr.length; i++) {
    if (parseFloat(arr[i].value)) tot += parseFloat(arr[i].value);
  }
  document.getElementById("total").innerHTML = tot.toFixed(2);
  if (tot == 0) {
    document.getElementById("submit").disabled = true;
  } else {
    document.getElementById("submit").disabled = false;
  }
}

function disableSubmitDefault() {
  document.getElementById("submit").disabled = true;
}

window.onload = disableSubmitDefault;
