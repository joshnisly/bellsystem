
$('#StartProcessBtn').bind('click', function(event)
{
    var statusHandle = doAjaxWithStatus({
        url: startUrl,
        data: {
            'should_fail': $('#ShouldFailCheck')[0].checked
        },
        statusElem: $('#ProcessStatus')
    });

    function cancelProcess()
    {
        statusHandle.cancel();
    }
    $('#CancelProcessBtn').bind('click', cancelProcess);
});


