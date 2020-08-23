$(document).ready(function() {
    display_contact_table(false);
});

function display_contact_table(visible) {
    $('.contact-table').css('display', visible ? 'contents' : 'none');
    $('.student-selected').css('display', visible ? 'none' : 'contents');
}