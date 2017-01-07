// THINGS THAT COULD BE ADDED
// - getFile from IfxUtil, makes getting a file in a lighbox and parsing the result easy.

function doAjax(options)
{
    
    function _onError()
    {
        var sErrMsg = 'A connection error has occurred.';
        if (onError)
            onError(sErrMsg);
        else
        {
            window.alert(sErrMsg);
            if (window.console)
                window.console.log(arguments);
        }
        return;
    }

    function _onSuccess(data)
    {
        var response = JSON.parse(data);
        if (response.error)
        {
            if (response.traceback && window.console)
                window.console.log(response.traceback);

            if (onError)
                onError(response.error);
            else
                window.alert(response.error);
            return;
        }
        if (onSuccess)
            onSuccess(response);
    }
    
    
    // Save success and error callbacks.
    var onSuccess = options['success'];
    var onError = options['error'];

    if ('data' in options)
    {
        options['data'] = JSON.stringify(options['data']);
        options['type'] = 'POST';
    }

    options['dataType'] = 'text';
    options['processData'] = 'false';
    options['success'] = _onSuccess;
    options['error'] = _onError;

    $.ajax(options);
}

function doAjaxWithStatus(options)
{
    var fnGlobals = {
        statusKey: '',
        updateInterval: '',
        status_url: '',
        cancel_url: ''
    };
    function onInterval()
    {
        function onStatusResponse(response)
        {
            if (response.state != 'running')
            {
                window.clearInterval(fnGlobals.updateInterval);
                fnGlobals.statusKey = '';
                if (options.finishedCallback)
                    options.finishedCallback(response);
            }

            if (options.statusElem)
                options.statusElem.text(response.status_str);

            if (options.statusCallback)
                options.statusCallback(response);
        }

        doAjax({
            url: fnGlobals.status_url,
            data: {'status_key': fnGlobals.statusKey},
            success: onStatusResponse
        });
    }
    
    doAjax({
        url: options['url'],
        data: options['data'],
        success: function(response)
        {
            fnGlobals.statusKey = response.status_key;
            fnGlobals.updateInterval = window.setInterval(onInterval, 1000);
            fnGlobals.status_url = response.status_url;
            fnGlobals.cancel_url = response.cancel_url;
            onInterval();
        }
    });

    function cancel(globals)
    {
        if (!globals.statusKey)
            return;

        doAjax({
            url: globals.cancel_url,
            data: {'status_key': globals.statusKey}
        });
    }
    return {
        cancel: cancel.bind(undefined, fnGlobals)
    };
}


function changeUrlQueryParameter(sUrl, sKey, sValue)
{
    var sBase, sQueryString, sFragment;
    var bShouldRemoveParm = sValue === false;

    // Yank off and ignore the fragment.
    var iFragmentPos = sUrl.indexOf('#');
    if (iFragmentPos >= 0)
    {
        sFragment = sUrl.substr(iFragmentPos);
        sUrl = sUrl.substr(0, iFragmentPos);
    }
    else
        sFragment = '';

    // Split the base from the query.
    var iQueryStringPos = sUrl.indexOf('?');
    if (iQueryStringPos >= 0)
    {
        sBase = sUrl.substr(0, iQueryStringPos);
        sQueryString = sUrl.substr(iQueryStringPos+1);
    }
    else
    {
        sBase = sUrl;
        sQueryString = '';
    }

    var asQueryString = [];
    if (sQueryString)
        asQueryString = sQueryString.split("&");

    var sNewKeyAndValue = encodeURIComponent(sKey) + "=" + encodeURIComponent(sValue);

    // Replace all existing parameters.
    var bHasSetParameter = false;
    for (var iCnt = 0; iCnt < asQueryString.length; iCnt++)
    {
        if (asQueryString[iCnt] === encodeURIComponent(sKey) ||
            asQueryString[iCnt].indexOf(encodeURIComponent(sKey) + "=") === 0)
        {
            if (!bShouldRemoveParm)
            {
                asQueryString[iCnt] = sNewKeyAndValue;
                bHasSetParameter = true;
            }
            else // Bool parms default to false when they are non-existent, so remove the false boolean parm.
            {
                asQueryString.splice(iCnt, 1);
                bHasSetParameter = true;
            }
        }
    }

    // Add a new parameter if the key could not be found.
    if (!bHasSetParameter)
    {
        if (!bShouldRemoveParm)
            asQueryString.push(sNewKeyAndValue);
    }

    return sBase + "?" + asQueryString.join("&") + sFragment;
}

function assert(bVal, sMsg)
{
    if(!bVal)
        alert('ASSERTION: \n' + sMsg);
}

/*
 * This function solves the problem of the value of "this" not persisting for callbacks.
 * (This function correctly maintains all parameters that are passed to the callback function.)
 *
 * Example usage:
 *
 *   function downloadData(callback)
 *   {
 *     var sData = "(download data here)";
 *     callback(sData);
 *   }
 *
 *   var myHandler = {};
 *   myHandler.onDownload = function(sData) { this._sData = sData; };
 *   downloadData(Callback.create(myHandler, myHandler.onDownload));
 *
 * In some situations, the callback's parameters need to be specified when the callback is created.
 * This is particularly cumbersome when creating callbacks in a loop, because it's not possible
 * to use a simple closure.
 *
 * Thanks to http://laurens.vd.oever.nl/weblog/items2005/closures/ for ideas on solving
 * Internet Explorer memory leaks.
 */
var _aClosureCache = [];
function createCallback(/*oObject, callback, aArgumentsOverride*/)
{
    // "this" will return the global object
    assert(typeof arguments[1] == "function");
    assert(!arguments[2] || arguments[2] instanceof Array);

    // cache the parameters in the member variable
    var iID = _aClosureCache.push(arguments)-1;
    assert(_aClosureCache[iID] == arguments);

    return function()
        {
            var oArguments = _aClosureCache[iID];
            var oObject = oArguments[0];
            var callback = oArguments[1];
            var aArgumentsOverride = oArguments[2];
            
            // If we have both normal arguments and an arguments override, pass in the normal arguments at the end
            if (aArgumentsOverride)
            {
                // Copy arguments array, so that the array is not affected for the next call.
                aArgumentsOverride = aArgumentsOverride.concat([]);
                for (var i = 0; i < arguments.length; i++)
                    aArgumentsOverride.push(arguments[i]);
            }

            return callback.apply(oObject, aArgumentsOverride || arguments);
        };
}

$.fn.invSetInputStyle = function()
{        
	return this.each(function()
    {
        $(this).toggleClass('live', $(this).val() !== '');
    });
};

function createElem(tagName, id, className)
{
    var elem = $(document.createElement(tagName));
    if (id)
        elem.attr('id', id);
    if (className)
        elem.addClass(className);
    return elem;
}


$.fn.appendNewChild = function(tagName, id, className)
{
    var aNewItems = [];
    this.each(function(index, elem) {
        var newElem = createElem(tagName, id, className)[0];
        if (id)
            newElem.id = id;
        if (className)
            newElem.className = className;
        elem.appendChild(newElem);
        aNewItems.push(newElem);
    });
    return $(aNewItems);
};

//Possible additions:
//    1) Consider using CSS animations instead of javascript animations for the fade effect.
//    2) Consider an option to disable the fade effect if it causes trouble over Remote Desktop.
//    3) Consider adding an onClose callback.
InvModal = {
    
	// title			string title of the lightbox
	// body				selector, elem, or jquery object to be inserted as content
	// buttonArray 		array of objects representing the buttons in the footer
	// widthPx			Optional width of the lighbox (default 540px)
	// doNoteAnimate	Do not fade in the lightbox
	// fnOnClose		Callback fired when the lighbox is closed
    open: function(title, body, buttonArray, widthPx, doNotAnimate, fnOnClose)
    {
        // Check for a malformed invocation.
        assert(!this._isOpen, 'You cannot open a lightbox while another lighbox is already open.');
        assert(typeof title == 'string', 'The modal title must be a string.');
        assert(body, 'Please provide a modal body.');
        
        // Establish defaults.
        buttonArray = buttonArray || [];        
        doNotAnimate = !!doNotAnimate || $.browser.msie;
        widthPx = widthPx || 540;
        for (var buttonCount = 0; buttonCount < buttonArray.length; buttonCount++)
        {
            buttonArray[buttonCount] = jQuery.extend({
                text: null,
                title: null,
                isPrimary: false,
                callback: null
            }, buttonArray[buttonCount]);
        }
        return this._open(title, body, buttonArray, widthPx, doNotAnimate, fnOnClose);
    },
    
    // Note: in mose cases, you should not use the replaceLiveContent paramter
	// since ideally modal dialogs should be discreet. Their state should persist only
	// while they are open. The exception to this is when there is form data such as
	// a file upload input that cannot be lost. Since this is the only scenario we are
	// attempting to cover, we strip off ALL events and hide the content before re-inserting it.
	close: function(doNotAnimate, replaceLiveContent)
    {
        if (this._isOpen)
        {
            // Delete the lightbox.
            this._modalElem.hide();
            this._toggleScrollbar();
            this._modalElem.remove();
            
            // Replace the template.
            if (replaceLiveContent)
            {
				var modalBody = this._modalElem.find('.invModalBody');
				modalBody.children().hide();
				modalBody.find('*').unbind();
                this._origBodyElemParent.append(modalBody.children());
            }
            else
                this._origBodyElemParent.append(this._origBodyElem);
            
            // Clear all state.
            this._modalElem = null;
            this._origBodyElemParent = null;
            this._origBodyElem = null;
            this._isUnclosable = false;
            this._isOpen = false;  
            
            // Hide the backdrop;
            if (doNotAnimate || $.browser.msie)
                this._backdropElem.hide();
            else
                this._backdropElem.fadeOut('fast');
			
			// Fire the user-defined close callback.
			this._fnOnClose();
        }
    },

    enableClose: function()
    {
        if (this._isOpen)
        {
            this._modalElem.find('.invModalClose').show();
            this._isUnclosable = false;
        }        
    },
    
    disableClose: function(bDisable)
    {
        if (this._isOpen)
        {
            this._modalElem.find('.invModalClose').hide();
            this._isUnclosable = true;
        }
    },

    // Private constant members.
    _backdropElem: null,
	
    // Private modal dependant members.
    _origBodyElem: null,
    _origBodyElemParent: null,
    _modalElem: null,
    _bodyOverflowStyle: null,
    _isOpen: false,
    _isUnclosable: false,
	_fnOnClose: null,

    // Private Methods.
    _init: function()
    {        
        // Create the modal backdrop.
        this._backdropElem = $('<div id="invModalBackdrop"></div>').appendTo('body');
        
        // Close on escape.
        $(document).keyup(createCallback(this, function(event)
        {
            if(this._isOpen && !this._isUnclosable && event.which === 27)
                this.close();
        }));
        
        // Close when the background is clicked.
        this._backdropElem.click(createCallback(this, function(event)
        {
            if (this._isOpen && !this._isUnclosable && this._modalElem.find(event.target).length === 0)
                this.close();
        }));

        // Fix display on window resize.
        $(window).resize(createCallback(this, this._fixVerticalPos));
    },
    
    _open: function(title, body, buttonArray, widthPx, doNotAnimate, fnOnClose)
    {
		// Save the close callback.
		this._fnOnClose = fnOnClose || function(){};
		
        // Create the modal parent.
        this._modalElem = $('<div class="invModal"></div>').css({
            'width': widthPx + 'px',
            'margin-left': (-widthPx / 2) + 'px'
        });
        
        // Create the modal header.
        var jHeader = $('<div class="invModalHeader"><span class="invModalClose invClose" title="Close">&#215;</span></div>');
        var jTitle = $('<h3 class="invModalTitle"></h3>').text(title);
        jHeader.appendTo(this._modalElem);
        jTitle.appendTo(jHeader);
        
        this._origBodyElem = $(body)
        this._origBodyElemParent = this._origBodyElem.parent();

        // Clone the body elem into the modal dialog and close the original.
        var body = $('<div class="invModalBody"></div>');
        body.append(this._origBodyElem.remove().clone().show()).appendTo(this._modalElem);
        
        // Create the modal footer (buttons).
        var footerElem = buttonArray ? $('<div class="invModalFooter"></div>') : $();
        footerElem.appendTo(this._modalElem);
        for (buttonCount = 0; buttonCount < buttonArray.length; buttonCount++)
        {
            // Create button.
            var oButtonOpts = buttonArray[buttonCount];
            var buttonElem = $('<button class="invBtn"></button>').appendTo(footerElem);
            
            // Configure button from opts.
            buttonElem.text(oButtonOpts.text);
            buttonElem.attr('title', oButtonOpts.title);
            buttonElem.toggleClass('invBtnPrimary', oButtonOpts.isPrimary);
            buttonElem.data('callback', oButtonOpts.callback);
        }

        // Calculate modal height. // The 5px addition fixes height calculation bugsin Chrome at non-standard zoom
        // levels and matches the diffrence between the top and bottom padding in InvGlobals.css.
        var tempElem = $('<div style="margin-left: -10000px">').appendTo('body');
        this._modalElem.css('max-height', this._modalElem.appendTo(tempElem).height() + 10 + 'px');
        this._modalElem.appendTo(this._backdropElem);
        tempElem.remove();
        
        // Attach event: Close when the "x" is closed.
        this._modalElem.find('.invModalClose').click(createCallback(this, this.close, [false]));
                
        // Fire callback on button click.
        this._modalElem.find('div.invModalFooter button.invBtn').click(createCallback(this, function(event)
        {
            var buttonElem = $(event.currentTarget);
            var callback = buttonElem.data('callback');
            if (!buttonElem.prop('disabled') && (!callback || callback(this._modalElem.find('.invModalBody')) !== false))
                    this.close();
        }));        
        
        // Set vertical position.
        if ($.browser.msie)
        {
            // In IE we use a timeout since setting the position directly
            // Causing IE to mis-report the element's height. This is OK,
            // because we also don't animate the lighbox in IE.
            this._modalElem.css('visibility', 'hidden');
            window.setTimeout(createCallback(this, function()
            {
                this._fixVerticalPos();
                this._modalElem.css('visibility', 'visible');
            }), 0);
        }
        else
        {
            this._backdropElem.show();
            this._fixVerticalPos();
            this._backdropElem.hide();
        }            
        
        // Hide the BODY's scrollbar.
        this._toggleScrollbar(true);
        
        // Open the lighbox.
        this._modalElem.hide();
        this._backdropElem.show();
        if (doNotAnimate)
            this._modalElem.show();
        else
            this._modalElem.fadeIn();
        this._isOpen = true;
    },
    
    _toggleScrollbar: function(bOpeningLightbox)
    {
        // In order to cover the BODY's scrollbar, we need to make the BODY
        // overflow:hidden and allow the lightbox backdrop to have its own scrollbar.
        // To avoid one-scrollbar-width jump of the page content when the BODY's
        // scrollbar is hidden, we add one-scrollbar-width of margin to the HTML element.
        // WARNING: This will not fix the jump for position:fixed elements.
        if (bOpeningLightbox) // Opening.
        {
            this._bodyOverflowStyle = $('body').css('overflow-y');
            var widthPxScrollbarVisible = $('body').width();
            var widthPxScrollbarHidden = $('body').css('overflow-y', 'hidden').width();
            $('html').css('margin-right', (widthPxScrollbarHidden - widthPxScrollbarVisible) + 'px');
        }
        else // Closing.
        {
            $('body').css('overflow-y', this._bodyOverflowStyle);
            $('html').css('margin-right', '0px');
        }
    },
        
    _fixVerticalPos: function(event)
    {
        if (!event || this._isOpen) // Fix the position if we are manually called when the lightbox is closed.
        {
            var topPx = Math.max((this._backdropElem.height() - this._modalElem.height()) / 3, 0);
            this._modalElem.css('top', topPx + 'px');                    
        }
    }
};

$(document).ready(function()
{
    // Input styles.
    $('input[type=text]').invSetInputStyle();
    $('body').delegate('input[type=text]', 'change', function()
    {
        $(this).invSetInputStyle();
    });

    InvModal._init();    
});
