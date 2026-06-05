// Signals toggle functionality
function initializeSignalsToggle() {
    const toggleButton = document.getElementById('toggleSignals');
    const signalsContainer = document.getElementById('signalsContainer');
    
    if (toggleButton && signalsContainer) {
        toggleButton.addEventListener('click', function() {
            const isVisible = !signalsContainer.classList.contains('hidden');
            
            if (isVisible) {
                signalsContainer.classList.add('hidden');
                toggleButton.innerHTML = '<i class="fas fa-chevron-down"></i> Click to Show Generated Signals';
            } else {
                signalsContainer.classList.remove('hidden');
                toggleButton.innerHTML = '<i class="fas fa-chevron-up"></i> Click to Hide Generated Signals';
            }
        });
    }
}

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', initializeSignalsToggle);

// Signal Generation and Management

// Signal class to represent a trading signal
class Signal {
    constructor(pair, direction, entryPrice, stopLoss, takeProfit, confidence, time) {
        this.pair = pair;
        this.direction = direction;
        this.entryPrice = entryPrice;
        this.stopLoss = stopLoss;
        this.takeProfit = takeProfit;
        this.confidence = confidence;
        this.time = time;
    }

    // Convert signal to HTML element
    toHTMLElement() {
        const signalCard = document.createElement('div');
        signalCard.className = 'signal-card';
        signalCard.style.cssText = 'background: rgba(255,255,255,0.07); border-radius: 12px; padding: 20px; box-shadow: 0 2px 16px #0002;';

        // Header with pair and time
        const header = document.createElement('div');
        header.style.cssText = 'display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px;';
        
        const pairDiv = document.createElement('div');
        pairDiv.style.cssText = 'font-size: 1.2rem; font-weight: bold;';
        pairDiv.textContent = this.pair;
        
        const timeDiv = document.createElement('div');
        timeDiv.style.cssText = 'font-size: 1.1rem; color: #00e6d0;';
        timeDiv.textContent = this.time;
        
        header.appendChild(pairDiv);
        header.appendChild(timeDiv);

        // Direction with icon
        const directionDiv = document.createElement('div');
        directionDiv.style.cssText = 'display: flex; align-items: center; gap: 10px; margin-bottom: 15px;';
        
        const icon = document.createElement('i');
        icon.className = this.direction === 'CALL' ? 'fas fa-arrow-up' : 'fas fa-arrow-down';
        icon.style.cssText = `color: ${this.direction === 'CALL' ? '#4CAF50' : '#f44336'}; font-size: 1.5rem;`;
        
        const directionText = document.createElement('span');
        directionText.style.cssText = `color: ${this.direction === 'CALL' ? '#4CAF50' : '#f44336'}; font-weight: bold;`;
        directionText.textContent = this.direction === 'CALL' ? 'BUY' : 'SELL';
        
        directionDiv.appendChild(icon);
        directionDiv.appendChild(directionText);

        // Confidence
        const confidenceDiv = document.createElement('div');
        confidenceDiv.style.cssText = 'display: flex; align-items: center; gap: 10px;';
        
        const confidenceIcon = document.createElement('i');
        confidenceIcon.className = 'fas fa-chart-line';
        confidenceIcon.style.cssText = 'color: #00e6d0;';
        
        const confidenceText = document.createElement('div');
        confidenceText.style.cssText = 'font-size: 0.9rem; color: #aaa;';
        confidenceText.innerHTML = `Signal Confidence: <span style="color: #fff;">${this.confidence.toFixed(2)}%</span>`;
        
        confidenceDiv.appendChild(confidenceIcon);
        confidenceDiv.appendChild(confidenceText);

        // Assemble card
        signalCard.appendChild(header);
        signalCard.appendChild(directionDiv);
        signalCard.appendChild(confidenceDiv);

        return signalCard;
    }
}

// Signal Manager class to handle signal operations
class SignalManager {
    constructor() {
        this.signals = [];
        this.container = document.getElementById('signalsContainer');
        this.toggleButton = document.getElementById('toggleSignals');
    }

    // Add a new signal
    addSignal(signal) {
        this.signals.push(signal);
        this.updateDisplay();
    }

    // Remove a signal
    removeSignal(index) {
        if (index >= 0 && index < this.signals.length) {
            this.signals.splice(index, 1);
            this.updateDisplay();
        }
    }

    // Clear all signals
    clearSignals() {
        this.signals = [];
        this.updateDisplay();
    }

    // Update the display
    updateDisplay() {
        if (!this.container) return;

        // Clear existing signals
        const signalsGrid = this.container.querySelector('.signals-grid');
        if (signalsGrid) {
            signalsGrid.innerHTML = '';
        }

        // Add signals to display
        this.signals.forEach(signal => {
            const signalElement = signal.toHTMLElement();
            signalsGrid.appendChild(signalElement);
        });

        // Update toggle button text
        if (this.toggleButton) {
            this.toggleButton.innerHTML = this.container.classList.contains('hidden')
                ? '<i class="fas fa-chevron-down"></i> Click to Show Generated Signals'
                : '<i class="fas fa-chevron-down"></i> Click to Hide Generated Signals';
        }
    }

    // Generate signals based on technical indicators
    generateSignals(pair, indicators, currentPrice) {
        const signals = [];
        const time = new Date().toLocaleTimeString();

        // Calculate overall confidence based on indicators
        let confidence = 0;
        let signalCount = 0;

        // RSI signals
        if (indicators.rsi !== undefined) {
            if (indicators.rsi > 70) {
                confidence += 30;
                signalCount++;
            } else if (indicators.rsi < 30) {
                confidence += 30;
                signalCount++;
            }
        }

        // MACD signals
        if (indicators.macd !== undefined) {
            if (indicators.macd > 0) {
                confidence += 25;
                signalCount++;
            } else {
                confidence += 25;
                signalCount++;
            }
        }

        // Bollinger Bands signals
        if (indicators.bb_upper !== undefined && indicators.bb_lower !== undefined) {
            if (currentPrice > indicators.bb_upper) {
                confidence += 25;
                signalCount++;
            } else if (currentPrice < indicators.bb_lower) {
                confidence += 25;
                signalCount++;
            }
        }

        // Stochastic RSI signals
        if (indicators.stoch_rsi_k !== undefined && indicators.stoch_rsi_d !== undefined) {
            if (indicators.stoch_rsi_k > 80 && indicators.stoch_rsi_d > 80) {
                confidence += 20;
                signalCount++;
            } else if (indicators.stoch_rsi_k < 20 && indicators.stoch_rsi_d < 20) {
                confidence += 20;
                signalCount++;
            }
        }

        // Calculate average confidence
        const avgConfidence = signalCount > 0 ? confidence / signalCount : 0;

        // Generate signals based on indicators
        if (avgConfidence >= 60) {
            const direction = indicators.rsi > 70 || currentPrice > indicators.bb_upper ? 'PUT' : 'CALL';
            const stopLoss = direction === 'CALL' ? currentPrice * 0.99 : currentPrice * 1.01;
            const takeProfit = direction === 'CALL' ? currentPrice * 1.02 : currentPrice * 0.98;

            signals.push(new Signal(
                pair,
                direction,
                currentPrice,
                stopLoss,
                takeProfit,
                avgConfidence,
                time
            ));
        }

        return signals;
    }
}

// Initialize signal manager
const signalManager = new SignalManager();

// Export for use in other files
window.signalManager = signalManager; 