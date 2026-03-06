// Clear localStorage deployment data
// Run this in the browser console (F12) to clear old mock deployments

console.log('Clearing old deployment data from localStorage...');

// Remove the deployments key
localStorage.removeItem('deployments');

console.log('✓ Deployment data cleared!');
console.log('Please refresh the page to load deployments from the backend.');

