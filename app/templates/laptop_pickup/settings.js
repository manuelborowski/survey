settings_id_list = [
    {id: "invite-contactmoment", type: 'boolean'},
    {id: "response-contactmoment", type: 'boolean'},
    {id: "template-invite-contactmoment", type: 'summernote'},
    {id: "template-response-contactmoment", type: 'summernote'},
]

$(document).ready(function() {

    $(".setting-slider").change(function() {
        jds = {}
        settings_id_list.forEach(setting => {
            jds[setting.id] = $('#' + setting.id).prop("checked");
        });
        $.getJSON(Flask.url_for('laptop_pickup.update_settings', {'jds': JSON.stringify(jds)}), function (data) {
            if (data.status) {
                enable_setting_controls(false);
            } else {
                bootbox.alert('Fout: kan settings niet aanpassen');
            }
        });
    });

    settings_id_list.forEach(setting => {
        if (setting.type == "summernote") {
            $("#" + setting.id).summernote({
                height: 200,
                minHeight: null,
                maxHeight: 800,
                lineHeights: ['0.6', '0.8', '1.0', '1.2', '1.4', '1.5', '2.0', '3.0'],
                toolbar: [
                    ['style', ['bold', 'italic', 'underline', 'clear']],
                    ['font', ['strikethrough', 'superscript', 'subscript']],
                    ['fontsize', ['fontsize']],
                    ['color', ['color']],
                    ['para', ['ul', 'ol', 'paragraph']],
                    ['insert', ['link',]],
                    ['height', ['height']],
                    ['view', ['fullscreen', 'codeview', 'help']],
                  ]
            });
        }
    });


    init_setting_controls()
    enable_setting_controls(false);
});

function enable_setting_controls(enable) {
    settings_id_list.forEach(setting => {
        if (setting.type == "summernote") {
            if (enable) {
                $('#' + setting.id).summernote("enable");
            } else {
                $('#' + setting.id).summernote("disable");
            }
        }
    });
    $(".setting-enable").prop("disabled", !enable);
}

function init_setting_controls() {
    settings_id_list.forEach(setting => {
        if(setting.type == "boolean") {
            $('#' + setting.id).prop("checked", info[setting.id]);
        } else if (setting.type == "summernote") {
            $('#' + setting.id).summernote('code', info[setting.id]);
        }
    });
}

function enable_change_settings() {
    bootbox.confirm("Bent u zeker dat u iets wil veranderen aan de settings?", function(result) {
        if (result) {
            enable_setting_controls(true);
        }
    });
}

function save_email_template(id) {
    bootbox.confirm("Bent u zeker dat u ĥet sjabloon wil bewaren?", function(result) {
        if (result) {
            var content = $("#" + id).summernote('code');
            data = {
                'template-id': id,
                'content': content,
            }
            $.post(Flask.url_for('update_email_template'), data, function (data) {
                if (data.status) {
                    enable_setting_controls(false);
               } else {
                    bootbox.alert('Fout: kan sjabloon niet aanpassen');
                }
            });
        }
    });
}

function trigger_email_activity(org, enable) {
    jds = {
        id: 'email-activity',
        org: org,
        state: enable,
    }
    $.getJSON(Flask.url_for('trigger_settings', {'jds': JSON.stringify(jds)}), function (data) {
        if (data.status) {
            enable_setting_controls(false);
        } else {
            bootbox.alert('Fout: kan setting niet activeren');
        }
    });
}