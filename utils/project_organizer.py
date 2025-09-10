import os

class ProjectOrganizer:
    _instance = None
    _initialized = False
    
    class SaveType:
        PROMPTS = "prompts"
        ASSETS = "assets"
        UNDERSTANDINGS = "understandings"
        SCRIPTS = "scripts"
        LOG = "log"
        VOICEOVERS = "voiceovers"
    
    @classmethod
    def init_all_subdirs(cls, **kwargs):
        instance = cls(**kwargs)
        save_types = [
            cls.SaveType.PROMPTS,
            cls.SaveType.ASSETS,
            cls.SaveType.UNDERSTANDINGS, 
            cls.SaveType.SCRIPTS,
            cls.SaveType.LOG,
            cls.SaveType.VOICEOVERS
        ]
        for save_type in save_types:
            save_dir = instance._dir_by_type(save_type)
            if not os.path.exists(save_dir):
                os.makedirs(save_dir)
    
    @classmethod
    def get_save_dir(cls, save_type: SaveType, **kwargs) -> str:
        instance = cls(**kwargs)
        return instance._dir_by_type(save_type) + "/"
    
    @classmethod
    def save(cls, save_type: SaveType, content, file_name: str, **kwargs) -> str:
        instance = cls(**kwargs)
        save_dir = instance._dir_by_type(save_type)
        if not os.path.exists(save_dir):
            os.makedirs(save_dir)
            
        try:
            # Check if content is binary (bytes) or text (str)
            if isinstance(content, bytes):
                with open(os.path.join(save_dir, file_name), "wb") as f:
                    f.write(content)
            else:
                with open(os.path.join(save_dir, file_name), "w") as f:
                    f.write(content)
            print(f"ProjectOrganizer: Saved {file_name} to {save_dir}")
            return os.path.join(save_dir, file_name)
        except Exception as e:
            print(f"ProjectOrganizer: Error saving {file_name} to {save_dir}: {e}")

    @classmethod
    def load(cls, save_type: SaveType, file_name: str, **kwargs) -> str:
        instance = cls(**kwargs)
        save_dir = instance._dir_by_type(save_type)
        if not os.path.exists(save_dir):
            os.makedirs(save_dir)
        try:
            with open(os.path.join(save_dir, file_name), "r") as f:
                print(f"ProjectOrganizer: Loaded {file_name} from {save_dir}")
                return f.read()
        except Exception as e:
            print(f"ProjectOrganizer: Error loading {file_name} from {save_dir}: {e}")
            return None
        
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(ProjectOrganizer, cls).__new__(cls)
        return cls._instance

    def __init__(self, workdir="workdir"):
        if not ProjectOrganizer._initialized:
            self.work_dir = workdir
            if not os.path.exists(self.work_dir):
                os.makedirs(self.work_dir)
            ProjectOrganizer._initialized = True
            
    def _dir_by_type(self, save_type: SaveType) -> str:
        return os.path.join(self.work_dir, save_type)
    
    def workdir_description_for_llm(self) -> str:
        pass