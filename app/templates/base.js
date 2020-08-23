function flash_messages(list) {
    for (var i=0; i<list.length; i++){
        var message = list[i];
        bootbox.alert(message);
    }
}
