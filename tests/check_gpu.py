import torch

print("torch:", torch.__version__, "| cuda:", torch.version.cuda)
print("disponibile:", torch.cuda.is_available())
print("device:", torch.cuda.get_device_name(0))
print("capability:", torch.cuda.get_device_capability(0))   # atteso (12, 0)
print("arch supportate:", torch.cuda.get_arch_list())        # deve contenere sm_120

a = torch.randn(4096, 4096, dtype=torch.bfloat16, device="cuda")
b = a @ a
torch.cuda.synchronize()
print("matmul bf16:", b.dtype, float(b.float().abs().mean()))
print("VRAM allocata (MB):", round(torch.cuda.memory_allocated() / 1e6, 1))