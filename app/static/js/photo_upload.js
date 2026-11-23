// Photos from the phone, before they leave it (Bitácora: new report and Editar).
// A phone photo weighs 3-8 MB; several together can exceed what the server (nginx) accepts in
// one request and take long on mobile data. Each JPEG/PNG/WebP is shrunk here to the same
// size the server keeps (2048 px, JPEG); HEIC and anything the browser can't open goes as is
// and the server converts it (app/utils/uploads.py).
window.TomatoPhotos = (() => {
    const MAX_SIDE = 2048;
    const QUALITY = 0.82;
    // nginx in production accepts 50 MB per request (README, Producción); leave room for the rest.
    const MAX_REQUEST_MB = 45;

    async function shrink(file) {
        if (!/^image\/(jpeg|png|webp)$/i.test(file.type) || typeof createImageBitmap !== 'function') return file;
        try {
            const bitmap = await createImageBitmap(file, { imageOrientation: 'from-image' });
            const scale = Math.min(1, MAX_SIDE / Math.max(bitmap.width, bitmap.height));
            const canvas = document.createElement('canvas');
            canvas.width = Math.round(bitmap.width * scale);
            canvas.height = Math.round(bitmap.height * scale);
            const ctx = canvas.getContext('2d');
            ctx.fillStyle = '#fff';  // PNG transparency becomes white, as on the server
            ctx.fillRect(0, 0, canvas.width, canvas.height);
            ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
            bitmap.close && bitmap.close();
            const blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/jpeg', QUALITY));
            if (!blob || blob.size >= file.size) return file;
            return new File([blob], file.name.replace(/\.[^.]+$/, '') + '.jpg', { type: 'image/jpeg' });
        } catch (e) {
            return file;  // the server checks and converts it
        }
    }

    // Shrinks every photo of a FormData field in place.
    async function shrinkField(formData, field = 'photos') {
        const files = formData.getAll(field).filter(f => f instanceof File && f.name);
        formData.delete(field);
        for (const file of files) formData.append(field, await shrink(file));
    }

    function megabytes(formData) {
        let bytes = 0;
        for (const [, value] of formData.entries()) bytes += value instanceof File ? value.size : String(value).length;
        return bytes / (1024 * 1024);
    }

    // Checked before sending, after shrinking: photos the phone can't shrink (HEIC/HEIF) can still
    // add up to more than the server takes in one go. "" when it fits.
    function tooBig(formData) {
        const mb = megabytes(formData);
        if (mb <= MAX_REQUEST_MB) return '';
        return `Las fotos suman ${mb.toLocaleString('es-CR', { maximumFractionDigits: 0 })} MB y se pueden mandar hasta `
            + `${MAX_REQUEST_MB} MB juntas. Quitá algunas y volvé a guardar; las demás las agregás después con Editar en el reporte.`;
    }

    // What to tell the person when the save failed: the server's own reason when it sent one,
    // otherwise what that error code means and what to do. Never just "error desconocido".
    async function failureMessage(response, formData) {
        let detail = '';
        try { detail = (await response.clone().json()).detail; } catch (e) {}
        if (Array.isArray(detail)) return 'Revisá los datos del formulario.';
        if (typeof detail === 'string' && detail) return detail;
        const code = response.status;
        if (code === 413) {
            const mb = formData ? megabytes(formData) : 0;
            const size = mb >= 0.1 ? ` (${mb.toLocaleString('es-CR', { maximumFractionDigits: 1 })} MB)` : '';
            return `Las fotos pesan demasiado para mandarlas juntas${size}: el servidor las rechazó (error 413). `
                + 'Quitá algunas y volvé a guardar; las demás las agregás después con Editar en el reporte.';
        }
        if (code === 504) return 'El servidor tardó demasiado en recibir el reporte (error 504), seguramente por las fotos. '
            + 'Probá con menos fotos; las demás se agregan después con Editar en el reporte.';
        if (code === 502 || code === 503) return `El sistema no respondió (error ${code}): puede que se estuviera reiniciando. `
            + 'Esperá un minuto y volvé a guardar.';
        if (code === 401 || code === 403) return `Tu sesión ya no permite guardar esto (error ${code}). `
            + 'Abrí TOMATO en otra pestaña, entrá de nuevo y volvé aquí a guardar.';
        if (code >= 500) return `El servidor tuvo un error al guardar (error ${code}). Probá de nuevo; `
            + 'si se repite, avisale al admin con la fecha y la hora.';
        return `No se pudo guardar (error ${code}). Probá de nuevo; si se repite, avisale al admin con la fecha y la hora.`;
    }

    return { shrink, shrinkField, tooBig, failureMessage };
})();
