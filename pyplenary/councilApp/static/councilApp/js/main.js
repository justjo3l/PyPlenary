function searchDelegateTable() {
  // Declare variables
  var input, filter,  searchTerms, table, tr, td, i, j, k, trElements, txtValue, toDisplay, fulfilled;
  input = document.getElementById("delegateSearchInput");
  filter = input.value.toUpperCase();
  searchTerms = filter.split(/\s+/);
  table = document.getElementById("delegateTable");
  tr = table.getElementsByTagName("tr");

  // Loop through all table rows, and hide those who don't match the search query
  for (i = 1; i < tr.length; i++) {
    trElements = tr[i].getElementsByTagName("td")

    allFulfilled = true;
    for (j = 0; j < searchTerms.length; j++) {
      fulfilled = false;
      for (k = 0; k < trElements.length; k++) {
        td = trElements[k];
        if (td) {
          txtValue = td.textContent || td.innerText;
          if (txtValue.toUpperCase().indexOf(searchTerms[j]) > -1) {
            fulfilled = true;
            break
          }
        }
      }
      if (!fulfilled) {
        allFulfilled = false;
        break
      }
    }
    if (allFulfilled) {
      tr[i].style.display = "";
    } else {
      tr[i].style.display = "none";
    }
  }
}

function getCookie(name) {
  var cookieValue = null;
  if (document.cookie && document.cookie !== '') {
    var cookies = document.cookie.split(';');
    for (var i = 0; i < cookies.length; i++) {
      var cookie = cookies[i].trim();
      if (cookie.substring(0, name.length + 1) === (name + '=')) {
        cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
        break;
      }
    }
  }
  return cookieValue;
}

function csrfHeaders() {
  return {'X-CSRFToken': getCookie('csrftoken')};
}

function download(filename, text) {
  var element = document.createElement('a');
  element.setAttribute('href', 'data:text/plain;charset=utf-8,' + encodeURIComponent(text));
  element.setAttribute('download', filename);

  element.style.display = 'none';
  document.body.appendChild(element);

  element.click();

  document.body.removeChild(element);
}
