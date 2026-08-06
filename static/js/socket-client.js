// Global Socket.IO / WebSocket connection fallback
let socket;
try {
    if (typeof io !== 'undefined') {
        socket = io();
        socket.on('connect', () => {
            console.log('Connected to WebSocket server');
        });
        socket.on('disconnect', () => {
            console.log('Disconnected from WebSocket server');
        });
    } else {
        socket = {
            on: () => {},
            emit: () => {},
            off: () => {}
        };
    }
} catch (e) {
    socket = {
        on: () => {},
        emit: () => {},
        off: () => {}
    };
}
