
function do_action(action, organization, id) {
    var msg = "";
    if(action == "remove-subscription") msg = "Wilt u deze uitnoding verwijderen?";
    if(action == "resend-contact-invite") msg = "Bent u zeker dat u de uitnodiging opnieuw wil sturen?";
    if(action == "remove-invite") msg = "Bent u zeker dat u e-mailadres wil verwijderen?";
    if(action == "toggle-activation") msg = "Bent u zeker dat u dit wil aanpassen?";
    if(action == "resend-not-responded") msg = "U stuur de uitnodiging nogmaals naar iedereeen die nog niet geantwoord heeft, ok?";


    bootbox.confirm(msg, function(result) {
        if (result) {
            jds = {
                action: action,
                organization: organization,
                id: id
            }
            $.getJSON(Flask.url_for('trigger_action', {'jds': JSON.stringify(jds)}), function (data) {
                if (data.status) {
                    var msg = data.msg ? data.msg : "Ok<br>";
                    bootbox.alert(msg, function() {
                        location.reload();
                    });
                } else {
                    var msg = data.msg ? data.msg : "Fout<br>";
                    bootbox.alert(msg, function() {
                        location.reload();
                    });
                }

                if (data.status) {
                } else {
                    var msg = data.msg ? data.msg : "";
                    bootbox.alert('Fout:<br>' + msg);
                }
            });
        }
    });
}

var invite_to_save_id = -1;

function invite_modal_save(organization) {
    var first_name = $("#invite-first-name").val();
    var last_name = $("#invite-last-name").val();
    var email = $("#invite-email").val();
    action = invite_to_save_id == -1 ? "add-invite" : "update-invite";
    jds = {
        action: action,
        organization: organization,
        first_name: first_name,
        last_name: last_name,
        email: email,
        id: invite_to_save_id,
    }
    invite_to_save_id = -1;
    $.getJSON(Flask.url_for('trigger_action', {'jds': JSON.stringify(jds)}), function (data) {
        if (data.status) {
            var msg = data.msg ? data.msg : "Ok<br>";
            bootbox.alert(msg, function() {
                location.reload();
            });
        } else {
            var msg = data.msg ? data.msg : "Fout<br>";
            bootbox.alert(msg, function() {
                location.reload();
            });
        }
    });

}

function edit_invite(id) {
    var button = $("#" + id);
    first_name = button.parent().parent().children()[0].innerText
    last_name = button.parent().parent().children()[1].innerText
    email = button.parent().parent().children()[2].innerText
    $("#invite-first-name").val(first_name);
    $("#invite-last-name").val(last_name);
    $("#invite-email").val(email);
    $("#invite-email").prop("disabled", true);
    invite_to_save_id = parseInt(id.split("-")[1]);
    $("#new-invite-modal").modal('show');
}