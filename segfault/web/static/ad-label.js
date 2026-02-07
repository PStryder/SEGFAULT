// Generate "Commercial Broadcast Channel" label with random serial
(function() {
  var hex = Array.from({length: 16}, function() {
    return Math.floor(Math.random() * 16).toString(16);
  }).join('').toUpperCase();
  var serial = hex.slice(0,4) + '-' + hex.slice(4,8) + '-' + hex.slice(8,12) + '-' + hex.slice(12,16);
  var text = 'Commercial Broadcast Channel ' + serial;

  // Update .ad-label elements (panel labels like <div class="label ad-label">)
  var labels = document.querySelectorAll('.ad-label');
  for (var i = 0; i < labels.length; i++) labels[i].textContent = text;

  // Update .ad-label-inner elements (ad-slots that serve as their own label)
  var inners = document.querySelectorAll('.ad-label-inner');
  for (var i = 0; i < inners.length; i++) inners[i].textContent = text;
})();
