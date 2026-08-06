// Shared configuration for TitleIndexing project
const TITLE_INDEXING_CONFIG = {
    types: [
        'Book Type Wrong',
        'Inst Type Wrong',
        'Remark Typo Error',
        'Clerk Number Wrong',
        'Volume Wrong',
        'Page Wrong',
        'Inst Date Wrong',
        'Inst Date is greater than File date',
        'File Date Wrong',
        'File Date is smaller than Inst date',
        'Amount Missing',
        'Amount Wrong capture',
        'Grontor Name wrong capture',
        'Grantor Name Missing',
        'Grantor Format wrong',
        'Typo Error',
        'Grantee Name wrong capture',
        'Grantee Name Missing',
        'Grantee Format wrong',
        'Suffix Missing',
        'Comment Missing',
        'Additional Entry Missing',
        'Both Side Wrong Entry Capture',
        'Died Comment Missing',
        'Sub Name Wrong',
        'Abstract Name Wrong',
        'Parcel ID Missing',
        'Address Missing',
        'Vol page Missing',
        'Micro Title entry Missing',
        'Acres Dividation skip',
        'Acress Wrong capture',
        'Comment Wrong capture',
        'Part of skip',
        'Others'
    ],
    fields: [
        'Book Type',
        'Instrument Type',
        'Remarks',
        'Cleark Number',
        'Volume',
        'Page',
        'Instrument Date',
        'Filing Date',
        'Lien Amount',
        'User Comment',
        'Grantor',
        'Grantee',
        'User Comment',
        'Subdivision',
        'Lot',
        'Block',
        'Section',
        'Abstract Name',
        'Acreage',
        'Legal Notes',
        'Prior Reference'
    ]
};

// Helper function to check if project is TitleIndexing
function isTitleIndexingProject(projectName) {
    return projectName && projectName.toLowerCase().includes('titleindexing');
}

// Master Data Cache for frontend (sessionStorage + Memory)
const MasterDataCache = {
    _memoryCache: new Map(),

    get(key) {
        if (this._memoryCache.has(key)) {
            const item = this._memoryCache.get(key);
            if (Date.now() < item.expiry) {
                return item.data;
            }
            this._memoryCache.delete(key);
        }
        try {
            const raw = sessionStorage.getItem(`mdc_${key}`);
            if (raw) {
                const parsed = JSON.parse(raw);
                if (Date.now() < parsed.expiry) {
                    this._memoryCache.set(key, parsed);
                    return parsed.data;
                }
                sessionStorage.removeItem(`mdc_${key}`);
            }
        } catch (e) {
            console.warn('SessionStorage read error:', e);
        }
        return null;
    },

    set(key, data, ttlSeconds = 300) {
        const item = {
            data: data,
            expiry: Date.now() + (ttlSeconds * 1000)
        };
        this._memoryCache.set(key, item);
        try {
            sessionStorage.setItem(`mdc_${key}`, JSON.stringify(item));
        } catch (e) {
            console.warn('SessionStorage write error:', e);
        }
    },

    async getOrFetch(key, fetchUrl, fetchOptions = {}, ttlSeconds = 300) {
        const cached = this.get(key);
        if (cached !== null) {
            return cached;
        }
        // Always send session cookie so DRF SessionAuthentication works.
        const opts = Object.assign({ credentials: 'same-origin' }, fetchOptions);
        const response = await fetch(fetchUrl, opts);
        if (!response.ok) {
            throw new Error(`HTTP error ${response.status}`);
        }
        const data = await response.json();
        this.set(key, data, ttlSeconds);
        return data;
    },

    invalidate(keyOrPrefix) {
        if (!keyOrPrefix) {
            this._memoryCache.clear();
            try {
                Object.keys(sessionStorage).forEach(k => {
                    if (k.startsWith('mdc_')) sessionStorage.removeItem(k);
                });
            } catch (e) {}
            return;
        }
        for (const k of this._memoryCache.keys()) {
            if (k.startsWith(keyOrPrefix)) {
                this._memoryCache.delete(k);
            }
        }
        try {
            Object.keys(sessionStorage).forEach(k => {
                if (k.startsWith(`mdc_${keyOrPrefix}`)) {
                    sessionStorage.removeItem(k);
                }
            });
        } catch (e) {}
    }
};

window.MasterDataCache = MasterDataCache;