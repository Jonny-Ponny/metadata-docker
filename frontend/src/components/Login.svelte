<!-- src/components/Login.svelte -->
<script>
  import { login, authError, theme, toggleTheme } from '../utils/index';
  
  let username = $state('');
  let password = $state('');
  let isLoading = $state(false);
  let error = $state('');
  
  async function handleSubmit(e) {
    e.preventDefault();
    isLoading = true;
    error = '';
    
    const result = await login(username, password);
    
    if (!result.success) {
      error = result.error;
    }
    
    isLoading = false;
  }
  
  // Sync authError store to local error state
  $effect(() => {
    if ($authError) {
      error = $authError;
    }
  });
</script>

<div class="login-container" class:dark={$theme === 'dark'}>
  <!-- Theme switch toggle (same as main app) -->
  <button class="theme-toggle" onclick={toggleTheme}>
    {#if $theme === "light"}
      <span>Light</span>
    {:else}
      <span>Dark</span>
    {/if}
  </button>
  
  <div class="login-box">
    <h1>Metadata</h1>
    <h2>Login</h2>
    
    <form onsubmit={handleSubmit}>
      <div class="form-group">
        <label for="username">Username</label>
        <input
          id="username"
          type="text"
          bind:value={username}
          placeholder="Enter username"
          required
          disabled={isLoading}
        />
      </div>
      
      <div class="form-group">
        <label for="password">Password</label>
        <input
          id="password"
          type="password"
          bind:value={password}
          placeholder="Enter password"
          required
          disabled={isLoading}
        />
      </div>
      
      {#if error}
        <div class="error-message">{error}</div>
      {/if}
      
      <button type="submit" disabled={isLoading}>
        {#if isLoading}
          Logging in...
        {:else}
          Login
        {/if}
      </button>
    </form>
  </div>
</div>

<style>
  .login-container {
    display: flex;
    justify-content: center;
    align-items: center;
    min-height: 100vh;
    background: linear-gradient(135deg, #dddddd 0%, #ebf1fa 100%);
    position: relative;
  }
  
  /* Dark mode gradient */
  .login-container.dark {
    background: linear-gradient(135deg, #2d3748 0%, #1a202c 100%);
  }
  
  /* Theme toggle button - matching main app style */
  .theme-toggle {
    position: fixed;
    bottom: 13px;
    left: 10px;
    background: #fd7d05;
    color: white;
    border: none;
    padding: 8px 16px;
    border-radius: 5px;
    cursor: pointer;
    font-size: 14px;
    font-weight: 500;
    z-index: 1001;
    transition: all 0.2s;
    display: flex;
    align-items: center;
    gap: 4px;
  }
  
  .theme-toggle:hover {
    background: #ff5e00;
    transform: translateY(-2px);
  }
  
  .login-box {
    background: white;
    padding: 2rem;
    border-radius: 8px;
    box-shadow: 0 10px 25px rgba(0,0,0,0.1);
    width: 100%;
    max-width: 400px;
  }
  
  /* Dark mode login box */
  .dark .login-box {
    background: #2d2d2d;
    box-shadow: 0 10px 25px rgba(0,0,0,0.3);
  }
  
  h1 {
    margin: 0 0 0.5rem 0;
    color: #333;
    text-align: center;
  }
  
  .dark h1 {
    color: #e0e0e0;
  }
  
  h2 {
    margin: 0 0 1.5rem 0;
    color: #666;
    text-align: center;
    font-weight: normal;
  }
  
  .dark h2 {
    color: #b0b0b0;
  }
  
  .form-group {
    margin-bottom: 1rem;
  }
  
  label {
    display: block;
    margin-bottom: 0.5rem;
    color: #555;
  }
  
  .dark label {
    color: #b0b0b0;
  }
  
  input {
    width: 100%;
    padding: 0.75rem;
    border: 1px solid #ddd;
    border-radius: 4px;
    font-size: 1rem;
    box-sizing: border-box;
    background: white;
    color: #333;
  }
  
  .dark input {
    background: #3d3d3d;
    border-color: #444;
    color: #e0e0e0;
  }
  
  input:focus {
    outline: none;
    border-color: #fd7d05;
    box-shadow: 0 0 0 2px rgba(253, 125, 5, 0.2);
  }
  
  .dark input:focus {
    border-color: #ff9f4b;
    box-shadow: 0 0 0 2px rgba(255, 159, 75, 0.2);
  }
  
  button[type="submit"] {
    width: 100%;
    padding: 0.75rem;
    background: #fd7d05;
    color: white;
    border: none;
    border-radius: 4px;
    font-size: 1rem;
    cursor: pointer;
    transition: all 0.2s;
  }
  
  button[type="submit"]:hover:not(:disabled) {
    background: #ff5e00;
    transform: translateY(-2px);
    /* box-shadow: 0 4px 12px rgba(253, 125, 5, 0.3); */
  }
  
  button[type="submit"]:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
  
  .error-message {
    background: #fee;
    color: #c33;
    padding: 0.75rem;
    border-radius: 4px;
    margin-bottom: 1rem;
    border: 1px solid #fcc;
  }
  
  .dark .error-message {
    background: #442222;
    color: #ff9999;
    border-color: #663333;
  }
</style>