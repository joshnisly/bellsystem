function renumberCheckboxes()
{
    var rows = $('.ActivationsTable TBODY TR');

    for (var i = 0; i < rows.length; i++)
    {
        var rowChecks = $(rows[i]).find('INPUT[type=checkbox]');
        for (var checkNum = 0; checkNum < rowChecks.length; checkNum++)
        {
            var check = rowChecks[checkNum];
            var name = check.getAttribute('name');
            var num = name.substr(name.lastIndexOf('_')+1);
            var newName = 'dow_' + (i+1) + '_' + num;
            check.setAttribute('name', newName);
        }
    }
}

function deleteRow(event)
{
    var row = $(event.target).closest('TR');
    row.remove();

    renumberCheckboxes();
}

function addRow(event)
{
    var row = $(event.target).closest('TR');
    var newRow = row.clone();
    console.log(newRow.find('INPUT[type=checkbox]'));
    newRow.find('INPUT[type=number]').val('');
    newRow.find('INPUT[type=checkbox]').removeAttr('checked');
    row[0].parentNode.insertBefore(newRow[0], row[0].nextSibling);

    renumberCheckboxes();
}

$(window).bind('load', function() {
   $(document.body).on('click', 'BUTTON.Delete', deleteRow);
   $(document.body).on('click', 'BUTTON.Add', addRow);
});