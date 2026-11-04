// TinyMCE image upload handler sending the CSRF token. Referenced by name from the
// widget config, so django-tinymce resolves it from window instead of using eval.
window.lmTinymceUploadHandler = function(blobInfo, progress) {
    return new Promise(function(resolve, reject) {
        const xhr = new XMLHttpRequest();
        xhr.open('POST', '/upload_media/');

        // Get CSRF token from cookie or form
        const csrftoken = document.querySelector('[name=csrfmiddlewaretoken]')?.value ||
                         document.cookie.split('; ').find(row => row.startsWith('csrftoken='))?.split('=')[1];

        if (csrftoken) {
            xhr.setRequestHeader('X-CSRFToken', csrftoken);
        }

        xhr.upload.onprogress = function(e) {
            progress(e.loaded / e.total * 100);
        };

        xhr.onload = function() {
            if (xhr.status === 403) {
                reject('HTTP Error: ' + xhr.status + ' - CSRF verification failed');
                return;
            }
            if (xhr.status < 200 || xhr.status >= 300) {
                reject('HTTP Error: ' + xhr.status);
                return;
            }

            const json = JSON.parse(xhr.responseText);
            if (!json || typeof json.location !== 'string') {
                reject('Invalid JSON: ' + xhr.responseText);
                return;
            }

            resolve(json.location);
        };

        xhr.onerror = function() {
            reject('Image upload failed due to a XHR Transport error. Code: ' + xhr.status);
        };

        const formData = new FormData();
        formData.append('file', blobInfo.blob(), blobInfo.filename());

        xhr.send(formData);
    });
};
