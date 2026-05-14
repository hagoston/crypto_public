import os
import sys
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader
from torch.utils.tensorboard import SummaryWriter
import pandas as pd
import numpy as np
from sklearn.preprocessing import StandardScaler, MinMaxScaler
from sklearn.model_selection import train_test_split
import joblib
from datetime import datetime

# Add project root to path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

from utils.logger_factory import get_logger

log = get_logger('train_model')

# --- Configuration ---
SEQ_LEN = 60  # 5 minutes of history (5s candles)
BATCH_SIZE = 64
EPOCHS = 20
LEARNING_RATE = 0.001
HIDDEN_DIM = 64
NUM_LAYERS = 2
DROPOUT = 0.2
MODEL_PATH = os.path.join(project_root, 'trader/models/neural_sniper_v1.pth')
SCALER_PATH = os.path.join(project_root, 'trader/models/scaler.pkl')
LOG_DIR = os.path.join(project_root, 'runs', f'neural_sniper_{datetime.now().strftime("%Y%m%d_%H%M%S")}')

# Ensure model directory exists
os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)

class SniperDataset(Dataset):
    def __init__(self, X, y):
        self.X = torch.FloatTensor(X)
        self.y = torch.FloatTensor(y)
        
    def __len__(self):
        return len(self.X)
    
    def __getitem__(self, idx):
        return self.X[idx], self.y[idx]

class LSTMClassifier(nn.Module):
    def __init__(self, input_dim, hidden_dim, num_layers, dropout):
        super(LSTMClassifier, self).__init__()
        self.hidden_dim = hidden_dim
        self.num_layers = num_layers
        
        self.lstm = nn.LSTM(input_dim, hidden_dim, num_layers, batch_first=True, dropout=dropout)
        self.fc = nn.Linear(hidden_dim, 1)
        self.sigmoid = nn.Sigmoid()
        
    def forward(self, x):
        # Initialize hidden state with zeros
        h0 = torch.zeros(self.num_layers, x.size(0), self.hidden_dim).to(x.device)
        c0 = torch.zeros(self.num_layers, x.size(0), self.hidden_dim).to(x.device)
        
        # Forward propagate LSTM
        out, _ = self.lstm(x, (h0, c0))  # out: tensor of shape (batch_size, seq_length, hidden_dim)
        
        # Decode the hidden state of the last time step
        out = self.fc(out[:, -1, :])
        out = self.sigmoid(out)
        return out

def create_sequences(data, labels, seq_len):
    xs = []
    ys = []
    for i in range(len(data) - seq_len):
        x = data[i:(i + seq_len)]
        y = labels[i + seq_len] # Label is for the period AFTER the sequence
        xs.append(x)
        ys.append(y)
    return np.array(xs), np.array(ys)

def main():
    # 1. Load Data
    data_path = os.path.join(project_root, 'training_data_5s.parquet')
    if not os.path.exists(data_path):
        log.error(f"Data file not found: {data_path}")
        return

    log.info("Loading data...")
    df = pd.read_parquet(data_path)
    
    # Drop rows with NaNs (just in case)
    df = df.dropna()
    
    # Features to use
    feature_cols = ['log_ret', 'atr', 'volatility', 'rsi', 'rel_vol', 'buy_ratio', 'trend', 'dist_vwap']
    target_col = 'target'
    
    log.info(f"Features: {feature_cols}")
    log.info(f"Total samples before sequencing: {len(df)}")
    
    # 2. Preprocessing
    
    X_list = []
    y_list = []
    
    mints = df['mint'].unique()
    log.info(f"Processing sequences for {len(mints)} mints...")
    
    scaler = StandardScaler()
    
    # Fit scaler on all data for simplicity in MVP
    df[feature_cols] = scaler.fit_transform(df[feature_cols])
    
    # Save scaler
    joblib.dump(scaler, SCALER_PATH)
    log.info(f"Saved scaler to {SCALER_PATH}")
    
    for mint in mints:
        mint_df = df[df['mint'] == mint].sort_index() # Ensure sorted by time (index is timestamp?)
        # Check if index is timestamp. In parquet it might be a column.
        if 'timestamp' in mint_df.columns:
            mint_df = mint_df.sort_values('timestamp')
        
        data = mint_df[feature_cols].values
        labels = mint_df[target_col].values
        
        if len(data) > SEQ_LEN:
            xs, ys = create_sequences(data, labels, SEQ_LEN)
            X_list.append(xs)
            y_list.append(ys)
            
    if not X_list:
        log.error("Not enough data to create sequences.")
        return
        
    X = np.concatenate(X_list)
    y = np.concatenate(y_list)
    
    log.info(f"Created {len(X)} sequences.")
    
    # 3. Train/Test Split
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, shuffle=True, random_state=42)
    
    # 4. Class Weights
    num_pos = np.sum(y_train == 1)
    num_neg = np.sum(y_train == 0)
    pos_weight = num_neg / num_pos
    log.info(f"Class Balance - Pos: {num_pos}, Neg: {num_neg}, Weight: {pos_weight:.2f}")
    
    # Convert to PyTorch Datasets
    train_dataset = SniperDataset(X_train, y_train)
    test_dataset = SniperDataset(X_test, y_test)
    
    train_loader = DataLoader(train_dataset, batch_size=BATCH_SIZE, shuffle=True)
    test_loader = DataLoader(test_dataset, batch_size=BATCH_SIZE, shuffle=False)
    
    # 5. Model Setup
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    log.info(f"Training on {device}")
    
    # Re-instantiate model without Sigmoid for BCEWithLogitsLoss
    class LSTMLogits(nn.Module):
        def __init__(self, input_dim, hidden_dim, num_layers, dropout):
            super(LSTMLogits, self).__init__()
            self.lstm = nn.LSTM(input_dim, hidden_dim, num_layers, batch_first=True, dropout=dropout)
            self.fc = nn.Linear(hidden_dim, 1)
            
        def forward(self, x):
            h0 = torch.zeros(NUM_LAYERS, x.size(0), HIDDEN_DIM).to(x.device)
            c0 = torch.zeros(NUM_LAYERS, x.size(0), HIDDEN_DIM).to(x.device)
            out, _ = self.lstm(x, (h0, c0))
            out = self.fc(out[:, -1, :])
            return out
            
    model = LSTMLogits(input_dim=len(feature_cols), hidden_dim=HIDDEN_DIM, num_layers=NUM_LAYERS, dropout=DROPOUT).to(device)
    pos_weight_tensor = torch.tensor([pos_weight]).to(device)
    criterion = nn.BCEWithLogitsLoss(pos_weight=pos_weight_tensor)
    
    optimizer = optim.Adam(model.parameters(), lr=LEARNING_RATE)
    
    # TensorBoard Writer
    writer = SummaryWriter(LOG_DIR)
    log.info(f"TensorBoard logging to {LOG_DIR}")
    
    # 6. Training Loop
    for epoch in range(EPOCHS):
        model.train()
        train_loss = 0
        
        for X_batch, y_batch in train_loader:
            X_batch, y_batch = X_batch.to(device), y_batch.to(device)
            
            optimizer.zero_grad()
            outputs = model(X_batch).squeeze()
            loss = criterion(outputs, y_batch)
            loss.backward()
            optimizer.step()
            
            train_loss += loss.item()
            
        avg_train_loss = train_loss / len(train_loader)
        
        # Validation
        model.eval()
        val_loss = 0
        correct = 0
        total = 0
        tp = 0
        fp = 0
        fn = 0
        
        with torch.no_grad():
            for X_batch, y_batch in test_loader:
                X_batch, y_batch = X_batch.to(device), y_batch.to(device)
                outputs = model(X_batch).squeeze()
                loss = criterion(outputs, y_batch)
                val_loss += loss.item()
                
                probs = torch.sigmoid(outputs)
                predicted = (probs > 0.5).float()
                
                total += y_batch.size(0)
                correct += (predicted == y_batch).sum().item()
                
                tp += ((predicted == 1) & (y_batch == 1)).sum().item()
                fp += ((predicted == 1) & (y_batch == 0)).sum().item()
                fn += ((predicted == 0) & (y_batch == 1)).sum().item()
                
        avg_val_loss = val_loss / len(test_loader)
        precision = tp / (tp + fp + 1e-9)
        recall = tp / (tp + fn + 1e-9)
        f1 = 2 * (precision * recall) / (precision + recall + 1e-9)
        accuracy = correct / total
        
        log.info(f"Epoch {epoch+1}/{EPOCHS} | Train Loss: {avg_train_loss:.4f} | Val Loss: {avg_val_loss:.4f} | Acc: {accuracy:.4f} | P: {precision:.2f} R: {recall:.2f} F1: {f1:.2f}")
        
        # Log to TensorBoard
        writer.add_scalar('Loss/train', avg_train_loss, epoch)
        writer.add_scalar('Loss/val', avg_val_loss, epoch)
        writer.add_scalar('Metrics/accuracy', accuracy, epoch)
        writer.add_scalar('Metrics/precision', precision, epoch)
        writer.add_scalar('Metrics/recall', recall, epoch)
        writer.add_scalar('Metrics/f1', f1, epoch)
        
    # 7. Save Model
    torch.save(model.state_dict(), MODEL_PATH)
    log.info(f"Model saved to {MODEL_PATH}")
    writer.close()

if __name__ == "__main__":
    main()
