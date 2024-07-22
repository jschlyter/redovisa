function updateTotal() {
  var arr = document.getElementsByClassName('amount');
  var tot = 0;
  for (var i = 0; i < arr.length; i++) {
    if (parseFloat(arr[i].value))
      tot += parseFloat(arr[i].value);
  }
  document.getElementById('total').innerHTML = tot.toFixed(2);
}
