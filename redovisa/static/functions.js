function updateForm() {
  // calculate total amount
  var amounts = document.getElementsByClassName("amount");
  var total = 0;
  for (let i = 0; i < amounts.length; i++) {
    if (parseFloat(amounts[i].value)) total += parseFloat(amounts[i].value);
  }
  document.getElementById("total").innerHTML = total.toFixed(2);

  // ensure account is set where amount > 0
  var form = document.forms["expense"];
  var missing_accounts = 0;
  for (let row = 0; row < amounts.length; row++) {
    var amount = parseFloat(form[row + ":" + "amount"].value);
    var account = form[row + ":" + "account"].value;
    if (amount > 0 && account == "") missing_accounts += 1;
  }

  if (total == 0 || missing_accounts > 0) {
    document.getElementById("submit").disabled = true;
  } else {
    document.getElementById("submit").disabled = false;
  }
}

function disableSubmitDefault() {
  document.getElementById("submit").disabled = true;
}

window.onload = disableSubmitDefault;
