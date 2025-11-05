import os
import sys
import json
import tempfile
import subprocess
from dataclasses import dataclass, asdict
from typing import Optional

from PyQt6.QtCore import Qt, QThread, pyqtSignal, QStandardPaths, QCoreApplication
from PyQt6.QtWidgets import (
    QApplication,
    QWidget,
    QGridLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QCheckBox,
    QComboBox,
    QPushButton,
    QPlainTextEdit,
    QHBoxLayout,
    QVBoxLayout,
    QMessageBox,
)


APP_ORG = "MassRDPLoader"
APP_NAME = "MassRDPLoader"


@dataclass
class AppConfig:
    host: str = "localhost"
    domain: str = ""
    password: str = ""
    start_index: int = 1
    end_index: int = 199
    auto_mode: bool = True
    auto_delay_seconds: int = 10

    share_clipboard: bool = False
    share_printers: bool = False
    share_comports: bool = False
    share_smartcards: bool = False
    share_posdevices: bool = False
    redirect_drives: bool = False
    redirect_devices: bool = False

    # audiomode: 0=在本机播放, 1=在远程播放, 2=不播放
    audio_mode: int = 2
    audio_capture: bool = False

    silent_connect: bool = True  # 使用 cmdkey 注入凭据免提示


class ConfigStore:
    def __init__(self):
        QCoreApplication.setOrganizationName(APP_ORG)
        QCoreApplication.setApplicationName(APP_NAME)
        base_dir = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppConfigLocation)
        if not base_dir:
            # Fallback to %APPDATA%/APP_ORG/APP_NAME
            base_dir = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), APP_ORG, APP_NAME)
        self.config_dir = base_dir
        self.config_path = os.path.join(self.config_dir, "config.json")
        os.makedirs(self.config_dir, exist_ok=True)

    def load(self) -> AppConfig:
        if not os.path.exists(self.config_path):
            cfg = AppConfig()
            self.save(cfg)
            return cfg
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return AppConfig(**{**asdict(AppConfig()), **data})
        except Exception:
            # 如果损坏，重建默认
            cfg = AppConfig()
            self.save(cfg)
            return cfg

    def save(self, cfg: AppConfig) -> None:
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(asdict(cfg), f, ensure_ascii=False, indent=2)


class RdpWorker(QThread):
    progress = pyqtSignal(str)
    currentUser = pyqtSignal(str)
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, cfg: AppConfig, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def _emit(self, text: str):
        self.progress.emit(text)

    def _run_cmd(self, args: list[str]) -> int:
        try:
            # 使用 list 避免 shell 解析问题
            completed = subprocess.run(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return completed.returncode
        except Exception as e:
            self._emit(f"命令执行失败: {' '.join(args)} -> {e}")
            return 1

    def _popen(self, args: list[str]) -> None:
        try:
            subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as e:
            self._emit(f"进程启动失败: {' '.join(args)} -> {e}")

    def _write_rdp_file(self, user_full: str) -> str:
        temp_dir = tempfile.gettempdir()
        rdp_path = os.path.join(temp_dir, f"remote_{user_full.replace('\\', '_')}.rdp")
        lines = [
            f"full address:s:{self.cfg.host}",
            f"username:s:{user_full}",
            "screen mode id:i:2",
            "session bpp:i:32",
            "authentication level:i:2",
            "enablecredsspsupport:i:1",
            # 凭据提示关闭，配合 cmdkey 免提示
            "prompt for credentials on client:i:0",
            "promptcredentialonce:i:0",
            # 资源重定向
            f"redirectclipboard:i:{1 if self.cfg.share_clipboard else 0}",
            f"redirectprinters:i:{1 if self.cfg.share_printers else 0}",
            f"redirectcomports:i:{1 if self.cfg.share_comports else 0}",
            f"redirectsmartcards:i:{1 if self.cfg.share_smartcards else 0}",
            f"redirectposdevices:i:{1 if self.cfg.share_posdevices else 0}",
            f"drivestoredirect:s:{'*' if self.cfg.redirect_drives else ''}",
            f"devicestoredirect:s:{'*' if self.cfg.redirect_devices else ''}",
            # 音频
            f"audiomode:i:{self.cfg.audio_mode}",
            f"audiocapturemode:i:{1 if self.cfg.audio_capture else 0}",
            "audioqualitymode:i:0",
        ]
        with open(rdp_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        return rdp_path

    def _delete_credentials(self):
        host = self.cfg.host
        # 忽略失败
        self._run_cmd(["cmdkey", "/delete:TERMSRV/" + host])
        self._run_cmd(["cmdkey", "/delete:TERMSRV/" + host + ":3389"])

    def _save_credentials(self, user_full: str):
        self._run_cmd(["cmdkey", "/generic:TERMSRV/" + self.cfg.host, 
                       "/user:" + user_full, "/pass:" + self.cfg.password])

    def run(self):
        start = max(1, int(self.cfg.start_index))
        end = max(start, int(self.cfg.end_index))
        # 非自动模式：只连接一个账号（起始序号），避免一次性全部打开
        if not self.cfg.auto_mode:
            end = start
        for i in range(start, end + 1):
            if self._cancel:
                break
            user = f"YD{i:03d}"
            user_full = f"{self.cfg.domain}\\{user}" if self.cfg.domain else user
            self.currentUser.emit(user_full)
            self._emit(f"处理用户 {user_full}")

            # 凭据处理
            self._delete_credentials()
            if self.cfg.silent_connect:
                self._emit("写入凭据以实现免提示登录")
                self._save_credentials(user_full)

            # 写入 rdp 并启动 mstsc
            rdp_file = self._write_rdp_file(user_full)
            self._emit(f"启动 mstsc: {rdp_file}")
            self._popen(["mstsc", rdp_file])

            # 自动模式延时
            delay = max(0, int(self.cfg.auto_delay_seconds)) if self.cfg.auto_mode else 0
            for _ in range(delay * 10):
                if self._cancel:
                    break
                self.msleep(100)
        self.finished.emit()


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Mass RDP Loader")
        self.store = ConfigStore()
        self.cfg = self.store.load()

        self._build_ui()
        self._load_cfg_to_ui()
        self.worker: Optional[RdpWorker] = None

    def _build_ui(self):
        grid = QGridLayout()

        row = 0
        grid.addWidget(QLabel("主机"), row, 0)
        self.host = QLineEdit()
        grid.addWidget(self.host, row, 1)

        row += 1
        grid.addWidget(QLabel("域(可留空)"), row, 0)
        self.domain = QLineEdit()
        grid.addWidget(self.domain, row, 1)

        row += 1
        grid.addWidget(QLabel("密码"), row, 0)
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        grid.addWidget(self.password, row, 1)

        row += 1
        grid.addWidget(QLabel("起始序号"), row, 0)
        self.start_index = QSpinBox()
        self.start_index.setRange(1, 500)
        grid.addWidget(self.start_index, row, 1)

        row += 1
        grid.addWidget(QLabel("结束序号"), row, 0)
        self.end_index = QSpinBox()
        self.end_index.setRange(1, 500)
        grid.addWidget(self.end_index, row, 1)

        row += 1
        self.auto_mode = QCheckBox("自动模式")
        grid.addWidget(self.auto_mode, row, 0)
        self.delay = QSpinBox()
        self.delay.setRange(0, 3600)
        self.delay.setSuffix(" 秒")
        grid.addWidget(self.delay, row, 1)

        # 资源重定向
        row += 1
        grid.addWidget(QLabel("资源重定向"), row, 0)
        res_layout = QHBoxLayout()
        self.cb_clip = QCheckBox("剪贴板")
        self.cb_prn = QCheckBox("打印机")
        self.cb_com = QCheckBox("串口")
        self.cb_smc = QCheckBox("智能卡")
        self.cb_pos = QCheckBox("POS设备")
        self.cb_drv = QCheckBox("本地驱动器")
        self.cb_dev = QCheckBox("即插即用设备")
        for w in [self.cb_clip, self.cb_prn, self.cb_com, self.cb_smc, self.cb_pos, self.cb_drv, self.cb_dev]:
            res_layout.addWidget(w)
        grid.addLayout(res_layout, row, 1)

        # 音频设置
        row += 1
        grid.addWidget(QLabel("远程音频"), row, 0)
        self.audio = QComboBox()
        self.audio.addItems(["在本机播放", "在远程播放", "不播放"])  # 0,1,2
        grid.addWidget(self.audio, row, 1)

        row += 1
        self.audio_cap = QCheckBox("启用本地录音")
        grid.addWidget(self.audio_cap, row, 1)

        row += 1
        self.silent = QCheckBox("免提示登录(保存凭据并直连)")
        grid.addWidget(self.silent, row, 1)

        # 操作按钮与状态
        row += 1
        btn_layout = QHBoxLayout()
        self.btn_start = QPushButton("开始")
        self.btn_stop = QPushButton("停止")
        self.btn_stop.setEnabled(False)
        btn_layout.addWidget(self.btn_start)
        btn_layout.addWidget(self.btn_stop)
        grid.addLayout(btn_layout, row, 0, 1, 2)

        row += 1
        self.lbl_current = QLabel("当前用户: -")
        grid.addWidget(self.lbl_current, row, 0, 1, 2)

        row += 1
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        grid.addWidget(self.log, row, 0, 1, 2)

        root = QVBoxLayout()
        root.addLayout(grid)
        self.setLayout(root)

        # 连接信号
        self.btn_start.clicked.connect(self.on_start)
        self.btn_stop.clicked.connect(self.on_stop)

    def _load_cfg_to_ui(self):
        self.host.setText(self.cfg.host)
        self.domain.setText(self.cfg.domain)
        self.password.setText(self.cfg.password)
        self.start_index.setValue(self.cfg.start_index)
        self.end_index.setValue(self.cfg.end_index)
        self.auto_mode.setChecked(self.cfg.auto_mode)
        self.delay.setValue(self.cfg.auto_delay_seconds)

        self.cb_clip.setChecked(self.cfg.share_clipboard)
        self.cb_prn.setChecked(self.cfg.share_printers)
        self.cb_com.setChecked(self.cfg.share_comports)
        self.cb_smc.setChecked(self.cfg.share_smartcards)
        self.cb_pos.setChecked(self.cfg.share_posdevices)
        self.cb_drv.setChecked(self.cfg.redirect_drives)
        self.cb_dev.setChecked(self.cfg.redirect_devices)

        # 音频
        # Combo 索引按 0,1,2 对应 audio_mode
        idx = 0 if self.cfg.audio_mode == 0 else 1 if self.cfg.audio_mode == 1 else 2
        self.audio.setCurrentIndex(idx)
        self.audio_cap.setChecked(self.cfg.audio_capture)

        self.silent.setChecked(self.cfg.silent_connect)

    def _collect_cfg_from_ui(self) -> AppConfig:
        cfg = AppConfig(
            host=self.host.text().strip(),
            domain=self.domain.text().strip(),
            password=self.password.text(),
            start_index=self.start_index.value(),
            end_index=self.end_index.value(),
            auto_mode=self.auto_mode.isChecked(),
            auto_delay_seconds=self.delay.value(),
            share_clipboard=self.cb_clip.isChecked(),
            share_printers=self.cb_prn.isChecked(),
            share_comports=self.cb_com.isChecked(),
            share_smartcards=self.cb_smc.isChecked(),
            share_posdevices=self.cb_pos.isChecked(),
            redirect_drives=self.cb_drv.isChecked(),
            redirect_devices=self.cb_dev.isChecked(),
            audio_mode={0:0, 1:1, 2:2}[self.audio.currentIndex()],
            audio_capture=self.audio_cap.isChecked(),
            silent_connect=self.silent.isChecked(),
        )
        return cfg

    def append_log(self, text: str):
        self.log.appendPlainText(text)

    def on_start(self):
        cfg = self._collect_cfg_from_ui()
        if not cfg.host:
            QMessageBox.warning(self, "提示", "主机不能为空")
            return
        if cfg.start_index > cfg.end_index:
            QMessageBox.warning(self, "提示", "起始序号不能大于结束序号")
            return

        # 保存配置
        self.cfg = cfg
        self.store.save(cfg)

        # 锁定UI
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        for w in [self.host, self.domain, self.password, self.start_index, self.end_index,
                  self.auto_mode, self.delay, self.cb_clip, self.cb_prn, self.cb_com, self.cb_smc,
                  self.cb_pos, self.cb_drv, self.cb_dev, self.audio, self.audio_cap, self.silent]:
            w.setEnabled(False)

        # 启动 worker
        self.worker = RdpWorker(cfg)
        self.worker.progress.connect(self.append_log)
        self.worker.currentUser.connect(lambda u: self.lbl_current.setText(f"当前用户: {u}"))
        self.worker.finished.connect(self.on_finished)
        self.worker.error.connect(self.append_log)
        self.worker.start()

    def on_stop(self):
        if self.worker:
            self.worker.cancel()
            self.append_log("用户取消，正在停止...")

    def on_finished(self):
        self.append_log("任务完成")
        self.worker = None
        # 解锁UI
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        for w in [self.host, self.domain, self.password, self.start_index, self.end_index,
                  self.auto_mode, self.delay, self.cb_clip, self.cb_prn, self.cb_com, self.cb_smc,
                  self.cb_pos, self.cb_drv, self.cb_dev, self.audio, self.audio_cap, self.silent]:
            w.setEnabled(True)
        # 非自动模式：自动将起始序号+1，便于再次点击开始打开下一个
        try:
            if not self.cfg.auto_mode and self.start_index.value() < self.end_index.value():
                self.start_index.setValue(self.start_index.value() + 1)
        except Exception:
            pass


def main():
    app = QApplication(sys.argv)
    w = MainWindow()
    w.resize(800, 600)
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()


