let itemIndex = 0;
function addItemRow() {
    const tpl = document.getElementById('itemRowTemplate');
    const clone = tpl.cloneNode(true);
    clone.classList.remove('d-none');
    clone.id = '';
    clone.innerHTML = clone.innerHTML.replaceAll('__prefix__', itemIndex);
    document.getElementById('itensWrapper').appendChild(clone);
    document.getElementById('id_itens-TOTAL_FORMS').value = ++itemIndex;
}
function removeItemRow(btn) {
    const row = btn.closest('.item-row');
    row.remove();
}
// adiciona uma linha inicial automaticamente
document.addEventListener('DOMContentLoaded', () => {
    if (document.getElementById('itemRowTemplate')) addItemRow();
});