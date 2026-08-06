// Full-screen image view function
function showFullImage(src, currentIndex = 0) {
    const allImages = Array.from(document.querySelectorAll('.image-grid img'));
    const totalImages = allImages.length;
    const showNavigation = totalImages > 1;
    
    const modal = document.createElement('div');
    modal.className = 'image-modal';
    modal.innerHTML = `
        <div class="modal-content">
            <div class="modal-header">
                <span class="image-counter">${currentIndex + 1} / ${totalImages}</span>
                <div class="zoom-controls">
                    <button class="zoom-btn zoom-in" title="Zoom In"><i class="fas fa-search-plus"></i></button>
                    <button class="zoom-btn zoom-out" title="Zoom Out"><i class="fas fa-search-minus"></i></button>
                    <button class="zoom-btn zoom-reset" title="Reset Zoom"><i class="fas fa-sync-alt"></i></button>
                </div>
                <span class="close-modal">&times;</span>
            </div>
            <div class="modal-image-container">
                ${showNavigation ? `
                    <button class="modal-nav-btn prev-btn" ${currentIndex === 0 ? 'disabled' : ''}>
                        <i class="fas fa-chevron-left"></i>
                    </button>
                ` : ''}
                <img src="${src}" alt="Full size screenshot" style="transform: scale(1) translate(0px, 0px); transition: transform 0.3s ease;">
                ${showNavigation ? `
                    <button class="modal-nav-btn next-btn" ${currentIndex === totalImages - 1 ? 'disabled' : ''}>
                        <i class="fas fa-chevron-right"></i>
                    </button>
                ` : ''}
            </div>
        </div>
    `;
    document.body.appendChild(modal);

    const img = modal.querySelector('img');
    let currentScale = 1;
    let isDragging = false;
    let startX, startY;
    let translateX = 0;
    let translateY = 0;
    const ZOOM_STEP = 0.25;
    const MAX_ZOOM = 3;
    const MIN_ZOOM = 0.5;

    // Zoom functions
    function zoomIn() {
        if (currentScale < MAX_ZOOM) {
            currentScale += ZOOM_STEP;
            updateTransform();
        }
    }

    function zoomOut() {
        if (currentScale > MIN_ZOOM) {
            currentScale -= ZOOM_STEP;
            updateTransform();
        }
    }

    function resetZoom() {
        currentScale = 1;
        translateX = 0;
        translateY = 0;
        updateTransform();
    }

    function updateTransform() {
        img.style.transform = `scale(${currentScale}) translate(${translateX}px, ${translateY}px)`;
    }

    // Drag functionality
    function startDrag(e) {
        if (currentScale > 1) {
            isDragging = true;
            startX = e.clientX - translateX;
            startY = e.clientY - translateY;
            img.style.cursor = 'grabbing';
            img.style.transition = 'none';
        }
    }

    function doDrag(e) {
        if (!isDragging) return;
        
        e.preventDefault();
        translateX = e.clientX - startX;
        translateY = e.clientY - startY;
        
        // Calculate bounds to prevent dragging too far
        const container = img.parentElement;
        const containerRect = container.getBoundingClientRect();
        const imgRect = img.getBoundingClientRect();
        
        const maxX = (imgRect.width * currentScale - containerRect.width) / 2;
        const maxY = (imgRect.height * currentScale - containerRect.height) / 2;
        
        translateX = Math.max(-maxX, Math.min(maxX, translateX));
        translateY = Math.max(-maxY, Math.min(maxY, translateY));
        
        updateTransform();
    }

    function endDrag() {
        if (isDragging) {
            isDragging = false;
            img.style.cursor = currentScale > 1 ? 'grab' : 'zoom-in';
            img.style.transition = 'transform 0.3s ease';
        }
    }

    // Add drag event listeners
    img.addEventListener('mousedown', startDrag);
    document.addEventListener('mousemove', doDrag);
    document.addEventListener('mouseup', endDrag);
    document.addEventListener('mouseleave', endDrag);

    // Add zoom event listeners
    modal.querySelector('.zoom-in').addEventListener('click', zoomIn);
    modal.querySelector('.zoom-out').addEventListener('click', zoomOut);
    modal.querySelector('.zoom-reset').addEventListener('click', resetZoom);

    // Add mouse wheel zoom
    img.addEventListener('wheel', (e) => {
        e.preventDefault();
        if (e.deltaY < 0) {
            zoomIn();
        } else {
            zoomOut();
        }
    });

    // Only add navigation functionality if there are multiple images
    if (showNavigation) {
        function updateModalImage(newIndex) {
            const newSrc = allImages[newIndex].src;
            img.src = newSrc;
            resetZoom(); // Reset zoom and position when changing images
            modal.querySelector('.image-counter').textContent = `${newIndex + 1} / ${totalImages}`;
            
            // Update button states
            modal.querySelector('.prev-btn').disabled = newIndex === 0;
            modal.querySelector('.next-btn').disabled = newIndex === totalImages - 1;
            
            currentIndex = newIndex;
        }

        // Event listeners for navigation
        modal.querySelector('.prev-btn').addEventListener('click', () => {
            if (currentIndex > 0) {
                updateModalImage(currentIndex - 1);
            }
        });

        modal.querySelector('.next-btn').addEventListener('click', () => {
            if (currentIndex < totalImages - 1) {
                updateModalImage(currentIndex + 1);
            }
        });

        // Keyboard navigation
        function handleKeyPress(e) {
            if (e.key === 'ArrowLeft' && currentIndex > 0) {
                updateModalImage(currentIndex - 1);
            } else if (e.key === 'ArrowRight' && currentIndex < totalImages - 1) {
                updateModalImage(currentIndex + 1);
            } else if (e.key === 'Escape') {
                closeModal();
            } else if (e.key === '+' || e.key === '=') {
                zoomIn();
            } else if (e.key === '-') {
                zoomOut();
            } else if (e.key === '0') {
                resetZoom();
            }
        }

        document.addEventListener('keydown', handleKeyPress);
    } else {
        // For single image, only handle Escape key and zoom
        function handleKeyPress(e) {
            if (e.key === 'Escape') {
                closeModal();
            } else if (e.key === '+' || e.key === '=') {
                zoomIn();
            } else if (e.key === '-') {
                zoomOut();
            } else if (e.key === '0') {
                resetZoom();
            }
        }
        document.addEventListener('keydown', handleKeyPress);
    }

    // Close modal function
    function closeModal() {
        if(typeof handleKeyPress !== 'undefined') {
            document.removeEventListener('keydown', handleKeyPress);
        }
        document.removeEventListener('mousemove', doDrag);
        document.removeEventListener('mouseup', endDrag);
        document.removeEventListener('mouseleave', endDrag);
        modal.remove();
    }

    modal.querySelector('.close-modal').onclick = closeModal;
    modal.onclick = (e) => {
        if (e.target === modal) closeModal();
    };
}

// Add image carousel navigation
document.addEventListener('DOMContentLoaded', function() {
    const prevBtn = document.getElementById('prev-image');
    const nextBtn = document.getElementById('next-image');

    if (prevBtn && nextBtn) {
        prevBtn.addEventListener('click', () => navigateImages('prev'));
        nextBtn.addEventListener('click', () => navigateImages('next'));
    }
});

function navigateImages(direction) {
    const images = document.querySelectorAll('#image-carousel img');
    if (!images.length) return;

    const currentIndex = Array.from(images).findIndex(img => img.classList.contains('active'));
    images[currentIndex].classList.remove('active');

    let newIndex;
    if (direction === 'next') {
        newIndex = (currentIndex + 1) % images.length;
    } else {
        newIndex = (currentIndex - 1 + images.length) % images.length;
    }

    images[newIndex].classList.add('active');
}
