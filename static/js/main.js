// Test JavaScript file
console.log('Static files working!');

// Add event listeners when document is ready
document.addEventListener('DOMContentLoaded', function() {
    console.log('Document ready!');
    
    // Test error handling
    window.onerror = function(msg, url, lineNo, columnNo, error) {
        console.error('Error: ' + msg + '\nURL: ' + url + '\nLine: ' + lineNo + '\nColumn: ' + columnNo + '\nError object: ' + JSON.stringify(error));
        return false;
    };
}); 